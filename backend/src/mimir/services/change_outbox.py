"""Change outbox event contract helpers.

This module contains event construction and database insertion helpers. Kafka
publication is introduced in later OUTBOX phases.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from psycopg.types.json import Json

from mimir.schemas.artifact import ArtifactResponse
from mimir.schemas.change_outbox import ChangeActor, ChangeOutboxEvent
from mimir.schemas.embedding import EmbeddingResponse
from mimir.schemas.relation import RelationResponse

CHANGE_EVENT_VERSION = 1
MIMIR_CHANGE_TOPIC = "mimir.changes.v1"
SCHEMA_NAME = "mimirdata"

EntityType = Literal["artifact", "relation", "embedding"]


@dataclass(frozen=True)
class ChangeOutboxRow:
    """Database row claimed by the outbox publisher."""

    event: ChangeOutboxEvent
    publish_attempts: int
    last_error: str | None


@dataclass(frozen=True)
class ChangeOutboxStatus:
    """Minimal health/status facts for the publisher."""

    unpublished_count: int
    oldest_unpublished_age_seconds: float | None


def build_kafka_key(tenant_id: int) -> str:
    """Build the v1 Kafka key.

    Tenant-level keying preserves ordering for related changes within a tenant.
    """
    return str(tenant_id)


def build_artifact_payload(artifact: ArtifactResponse) -> dict[str, Any]:
    """Build compact artifact facts for the change stream."""
    return {
        "artifact_type": artifact.artifact_type,
        "parent_artifact_id": _uuid_or_none(artifact.parent_artifact_id),
        "source": artifact.source,
        "source_system": artifact.source_system,
        "external_id": artifact.external_id,
        "content_hash": artifact.content_hash,
    }


def build_relation_payload(relation: RelationResponse) -> dict[str, Any]:
    """Build compact relation facts for the change stream."""
    return {
        "relation_type": relation.relation_type,
        "source_id": str(relation.source_id),
        "target_id": str(relation.target_id),
        "confidence": relation.confidence,
    }


def build_embedding_payload(embedding: EmbeddingResponse) -> dict[str, Any]:
    """Build compact embedding facts for the change stream."""
    return {
        "artifact_id": str(embedding.artifact_id),
        "embedding_type": embedding.embedding_type,
    }


def build_change_event(
    *,
    event_id: UUID,
    tenant_id: int,
    sequence: int,
    entity_type: EntityType,
    entity_id: UUID,
    occurred_at: datetime,
    provenance_event_id: UUID | None = None,
    correlation_id: UUID | None = None,
    actor_type: str | None = None,
    actor_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> ChangeOutboxEvent:
    """Build a versioned change event from outbox row facts."""
    actor = ChangeActor(type=actor_type, id=actor_id) if actor_type else None
    return ChangeOutboxEvent(
        event_id=event_id,
        event_version=CHANGE_EVENT_VERSION,
        tenant_id=tenant_id,
        sequence=sequence,
        entity_type=entity_type,
        entity_id=entity_id,
        action="create",
        occurred_at=occurred_at,
        provenance_event_id=provenance_event_id,
        correlation_id=correlation_id,
        actor=actor,
        payload=payload or {},
    )


def build_artifact_change_event(
    artifact: ArtifactResponse, **event_kwargs: Any
) -> ChangeOutboxEvent:
    """Build a change event for an artifact create."""
    return build_change_event(
        tenant_id=artifact.tenant_id,
        entity_type="artifact",
        entity_id=artifact.id,
        payload=build_artifact_payload(artifact),
        **event_kwargs,
    )


def build_relation_change_event(
    relation: RelationResponse, **event_kwargs: Any
) -> ChangeOutboxEvent:
    """Build a change event for a relation create."""
    return build_change_event(
        tenant_id=relation.tenant_id,
        entity_type="relation",
        entity_id=relation.id,
        payload=build_relation_payload(relation),
        **event_kwargs,
    )


def build_embedding_change_event(
    embedding: EmbeddingResponse, **event_kwargs: Any
) -> ChangeOutboxEvent:
    """Build a change event for an embedding create."""
    return build_change_event(
        tenant_id=embedding.tenant_id,
        entity_type="embedding",
        entity_id=embedding.id,
        payload=build_embedding_payload(embedding),
        **event_kwargs,
    )


async def insert_change_event(
    *,
    conn: Any,
    tenant_id: int,
    entity_type: EntityType,
    entity_id: UUID,
    provenance_event_id: UUID,
    actor_type: str,
    actor_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> ChangeOutboxEvent:
    """Insert a retained outbox row using an existing transaction."""
    result = await conn.execute(
        f"""
        INSERT INTO {SCHEMA_NAME}.change_outbox
            (tenant_id, entity_type, entity_id, action, provenance_event_id,
             actor_type, actor_id, payload)
        VALUES (%s, %s, %s, 'create', %s, %s, %s, %s)
        RETURNING id, tenant_id, sequence, entity_type, entity_id, action,
                  occurred_at, provenance_event_id, correlation_id,
                  actor_type, actor_id, payload
        """,
        (
            tenant_id,
            entity_type,
            str(entity_id),
            str(provenance_event_id),
            actor_type,
            actor_id,
            Json(payload or {}),
        ),
    )
    row = await result.fetchone()
    return _row_to_change_event(row)


async def fetch_unpublished_events(
    *,
    conn: Any,
    limit: int,
) -> list[ChangeOutboxRow]:
    """Claim due unpublished rows in replay order.

    Callers must run this inside a transaction and either mark rows published,
    record failures, or roll back to release the row locks.
    """
    result = await conn.execute(
        f"""
        SELECT id, tenant_id, sequence, entity_type, entity_id, action,
               occurred_at, provenance_event_id, correlation_id,
               actor_type, actor_id, payload, publish_attempts, last_error
        FROM {SCHEMA_NAME}.change_outbox
        WHERE published_at IS NULL
          AND next_attempt_at <= now()
        ORDER BY sequence
        LIMIT %s
        FOR UPDATE SKIP LOCKED
        """,
        (limit,),
    )
    rows = await result.fetchall()
    return [_row_to_outbox_row(row) for row in rows]


async def mark_published(*, conn: Any, event_id: UUID) -> None:
    """Mark a row published after Kafka acknowledgement."""
    await conn.execute(
        f"""
        UPDATE {SCHEMA_NAME}.change_outbox
        SET published_at = now(),
            last_error = NULL
        WHERE id = %s
          AND published_at IS NULL
        """,
        (str(event_id),),
    )


async def record_publish_failure(
    *,
    conn: Any,
    event_id: UUID,
    error: str,
    retry_after_seconds: int,
) -> None:
    """Record a failed publish attempt and persist retry timing."""
    await conn.execute(
        f"""
        UPDATE {SCHEMA_NAME}.change_outbox
        SET publish_attempts = publish_attempts + 1,
            last_error = %s,
            next_attempt_at = now() + (%s * interval '1 second')
        WHERE id = %s
          AND published_at IS NULL
        """,
        (error, retry_after_seconds, str(event_id)),
    )


def calculate_retry_delay_seconds(
    publish_attempts: int,
    *,
    base_seconds: int = 1,
    max_seconds: int = 300,
) -> int:
    """Calculate bounded exponential backoff for the next failure."""
    if publish_attempts < 0:
        raise ValueError("publish_attempts must be non-negative")
    if base_seconds < 1:
        raise ValueError("base_seconds must be at least 1")
    if max_seconds < base_seconds:
        raise ValueError("max_seconds must be at least base_seconds")

    return min(max_seconds, base_seconds * (2**publish_attempts))


async def get_outbox_status(*, conn: Any) -> ChangeOutboxStatus:
    """Return backlog size and age of the oldest unpublished event."""
    result = await conn.execute(
        f"""
        SELECT COUNT(*),
               EXTRACT(EPOCH FROM (now() - MIN(occurred_at)))
        FROM {SCHEMA_NAME}.change_outbox
        WHERE published_at IS NULL
        """
    )
    row = await result.fetchone()
    age = float(row[1]) if row[1] is not None else None
    return ChangeOutboxStatus(
        unpublished_count=row[0], oldest_unpublished_age_seconds=age
    )


def _row_to_outbox_row(row: tuple) -> ChangeOutboxRow:
    event = _row_to_change_event(row[:12])
    return ChangeOutboxRow(event=event, publish_attempts=row[12], last_error=row[13])


def _row_to_change_event(row: tuple) -> ChangeOutboxEvent:
    return build_change_event(
        event_id=UUID(row[0]) if isinstance(row[0], str) else row[0],
        tenant_id=row[1],
        sequence=row[2],
        entity_type=row[3],
        entity_id=UUID(row[4]) if isinstance(row[4], str) else row[4],
        occurred_at=row[6],
        provenance_event_id=UUID(row[7]) if isinstance(row[7], str) else row[7],
        correlation_id=UUID(row[8]) if isinstance(row[8], str) else row[8],
        actor_type=row[9],
        actor_id=row[10],
        payload=row[11],
    )


def _uuid_or_none(value: UUID | None) -> str | None:
    return str(value) if value is not None else None
