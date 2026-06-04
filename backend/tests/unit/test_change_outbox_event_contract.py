"""Tests for Mimir change outbox event contract helpers."""

from datetime import UTC, datetime
from uuid import UUID

from mimir.schemas.artifact import ArtifactResponse
from mimir.schemas.embedding import EmbeddingResponse
from mimir.schemas.relation import RelationResponse
from mimir.services.change_outbox import (
    MIMIR_CHANGE_TOPIC,
    build_artifact_change_event,
    build_embedding_change_event,
    build_kafka_key,
    build_relation_change_event,
)

EVENT_ID = UUID("019e9052-2ab7-71ca-b202-73d3104a8d73")
PROVENANCE_ID = UUID("019e9052-51aa-78d5-8a9e-42a6db30c2d0")
CORRELATION_ID = UUID("019e9052-7000-744e-87de-2f2fa9d85f3c")
OCCURRED_AT = datetime(2026, 6, 4, 1, 49, 24, 535000, tzinfo=UTC)


def test_change_topic_and_key_are_tenant_scoped():
    """The v1 stream uses one topic and tenant-level Kafka keying."""
    assert MIMIR_CHANGE_TOPIC == "mimir.changes.v1"
    assert build_kafka_key(42) == "42"


def test_artifact_change_event_contract_is_compact():
    """Artifact events should expose compact facts, not full content."""
    artifact = ArtifactResponse(
        id=UUID("019e9052-aaaa-7000-9000-000000000001"),
        tenant_id=1,
        artifact_type="document",
        parent_artifact_id=UUID("019e9052-bbbb-7000-9000-000000000002"),
        title="A document",
        content="Large content should not be duplicated in the event",
        content_hash="abc123",
        source="import",
        source_system="email",
        external_id="message-1",
        metadata={"sensitive": "not emitted by default"},
        created_at=OCCURRED_AT,
    )

    event = build_artifact_change_event(
        artifact,
        event_id=EVENT_ID,
        sequence=12345,
        occurred_at=OCCURRED_AT,
        provenance_event_id=PROVENANCE_ID,
        correlation_id=CORRELATION_ID,
        actor_type="api_client",
        actor_id="efforts",
    )
    event_json = event.model_dump(mode="json", exclude_none=True)

    assert event_json == {
        "event_id": str(EVENT_ID),
        "event_version": 1,
        "tenant_id": 1,
        "sequence": 12345,
        "entity_type": "artifact",
        "entity_id": str(artifact.id),
        "action": "create",
        "occurred_at": "2026-06-04T01:49:24.535000Z",
        "provenance_event_id": str(PROVENANCE_ID),
        "correlation_id": str(CORRELATION_ID),
        "actor": {"type": "api_client", "id": "efforts"},
        "payload": {
            "artifact_type": "document",
            "parent_artifact_id": str(artifact.parent_artifact_id),
            "source": "import",
            "source_system": "email",
            "external_id": "message-1",
            "content_hash": "abc123",
        },
    }
    assert "content" not in event_json["payload"]
    assert "metadata" not in event_json["payload"]


def test_relation_change_event_contract():
    """Relation events expose graph edge facts."""
    relation = RelationResponse(
        id=UUID("019e9052-4f16-7b94-9315-3d860b16cf55"),
        tenant_id=1,
        source_id=UUID("019e9052-aaaa-7000-9000-000000000001"),
        target_id=UUID("019e9052-bbbb-7000-9000-000000000002"),
        relation_type="derived_from",
        confidence=0.8,
        metadata={},
        created_at=OCCURRED_AT,
    )

    event = build_relation_change_event(
        relation,
        event_id=EVENT_ID,
        sequence=12345,
        occurred_at=OCCURRED_AT,
        provenance_event_id=PROVENANCE_ID,
    )
    event_json = event.model_dump(mode="json", exclude_none=True)

    assert event_json["entity_type"] == "relation"
    assert event_json["payload"] == {
        "relation_type": "derived_from",
        "source_id": str(relation.source_id),
        "target_id": str(relation.target_id),
        "confidence": 0.8,
    }


def test_embedding_change_event_contract():
    """Embedding events expose artifact and embedding type facts."""
    embedding = EmbeddingResponse(
        id=UUID("019e9052-4f16-7b94-9315-3d860b16cf55"),
        tenant_id=1,
        artifact_id=UUID("019e9052-aaaa-7000-9000-000000000001"),
        embedding_type="nomic-embed-text",
        metadata={},
        created_at=OCCURRED_AT,
    )

    event = build_embedding_change_event(
        embedding,
        event_id=EVENT_ID,
        sequence=12345,
        occurred_at=OCCURRED_AT,
        provenance_event_id=PROVENANCE_ID,
    )
    event_json = event.model_dump(mode="json", exclude_none=True)

    assert event_json["entity_type"] == "embedding"
    assert event_json["payload"] == {
        "artifact_id": str(embedding.artifact_id),
        "embedding_type": "nomic-embed-text",
    }
