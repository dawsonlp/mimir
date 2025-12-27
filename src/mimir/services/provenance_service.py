"""Provenance service - database operations for audit trail tracking."""

import json
from datetime import datetime

from mimir.database import get_connection
from mimir.models import SCHEMA_NAME
from mimir.schemas.provenance import (
    EntityProvenanceResponse,
    ProvenanceAction,
    ProvenanceActorType,
    ProvenanceEntityType,
    ProvenanceEventCreate,
    ProvenanceEventListResponse,
    ProvenanceEventResponse,
)


def _row_to_response(row: tuple) -> ProvenanceEventResponse:
    """Convert a database row to a ProvenanceEventResponse."""
    return ProvenanceEventResponse(
        id=row[0],
        tenant_id=row[1],
        entity_type=row[2],
        entity_id=row[3],
        action=row[4],
        actor_type=row[5],
        actor_id=row[6],
        actor_name=row[7],
        timestamp=row[8],
        reason=row[9],
        changes=row[10],
        metadata=row[11] or {},
        related_entity_type=row[12],
        related_entity_id=row[13],
        correlation_id=row[14],
        request_id=row[15],
        created_at=row[16],
    )


async def record_event(
    tenant_id: int, data: ProvenanceEventCreate
) -> ProvenanceEventResponse:
    """Record a new provenance event (append-only)."""
    async with get_connection() as conn:
        result = await conn.execute(
            f"""
            INSERT INTO {SCHEMA_NAME}.provenance_events
                (tenant_id, entity_type, entity_id, action, actor_type, actor_id,
                 actor_name, reason, changes, metadata, related_entity_type,
                 related_entity_id, correlation_id, request_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id, tenant_id, entity_type, entity_id, action, actor_type,
                      actor_id, actor_name, timestamp, reason, changes, metadata,
                      related_entity_type, related_entity_id, correlation_id,
                      request_id, created_at
            """,
            (
                tenant_id,
                data.entity_type.value,
                data.entity_id,
                data.action.value,
                data.actor_type.value,
                data.actor_id,
                data.actor_name,
                data.reason,
                json.dumps(data.changes) if data.changes else None,
                json.dumps(data.metadata) if data.metadata else "{}",
                data.related_entity_type.value if data.related_entity_type else None,
                data.related_entity_id,
                data.correlation_id,
                data.request_id,
            ),
        )
        row = await result.fetchone()
        await conn.commit()

    return _row_to_response(row)


async def record_simple_event(
    tenant_id: int,
    entity_type: ProvenanceEntityType,
    entity_id: int,
    action: ProvenanceAction,
    actor_type: ProvenanceActorType = ProvenanceActorType.api_client,
    actor_id: str | None = None,
    actor_name: str | None = None,
    reason: str | None = None,
    changes: dict | None = None,
    metadata: dict | None = None,
    request_id: str | None = None,
) -> ProvenanceEventResponse:
    """Convenience function to record a provenance event with common defaults."""
    data = ProvenanceEventCreate(
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        actor_type=actor_type,
        actor_id=actor_id,
        actor_name=actor_name,
        reason=reason,
        changes=changes,
        metadata=metadata or {},
        request_id=request_id,
    )
    return await record_event(tenant_id, data)


async def get_entity_provenance(
    tenant_id: int,
    entity_type: str,
    entity_id: int,
    page: int = 1,
    page_size: int = 50,
) -> EntityProvenanceResponse:
    """Get provenance history for a specific entity."""
    offset = (page - 1) * page_size

    async with get_connection() as conn:
        # Get total count
        count_result = await conn.execute(
            f"""
            SELECT COUNT(*) FROM {SCHEMA_NAME}.provenance_events
            WHERE tenant_id = %s AND entity_type = %s AND entity_id = %s
            """,
            (tenant_id, entity_type, entity_id),
        )
        total = (await count_result.fetchone())[0]

        # Get events (most recent first)
        result = await conn.execute(
            f"""
            SELECT id, tenant_id, entity_type, entity_id, action, actor_type,
                   actor_id, actor_name, timestamp, reason, changes, metadata,
                   related_entity_type, related_entity_id, correlation_id,
                   request_id, created_at
            FROM {SCHEMA_NAME}.provenance_events
            WHERE tenant_id = %s AND entity_type = %s AND entity_id = %s
            ORDER BY timestamp DESC
            LIMIT %s OFFSET %s
            """,
            (tenant_id, entity_type, entity_id, page_size, offset),
        )
        rows = await result.fetchall()

    events = [_row_to_response(row) for row in rows]

    return EntityProvenanceResponse(
        entity_type=ProvenanceEntityType(entity_type),
        entity_id=entity_id,
        events=events,
        total=total,
    )


async def list_events(
    tenant_id: int,
    page: int = 1,
    page_size: int = 50,
    entity_type: str | None = None,
    action: str | None = None,
    actor_type: str | None = None,
    actor_id: str | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    correlation_id: str | None = None,
) -> ProvenanceEventListResponse:
    """List provenance events with pagination and filtering."""
    offset = (page - 1) * page_size

    async with get_connection() as conn:
        # Build dynamic WHERE clause
        where_parts = ["tenant_id = %s"]
        params: list = [tenant_id]

        if entity_type:
            where_parts.append("entity_type = %s")
            params.append(entity_type)
        if action:
            where_parts.append("action = %s")
            params.append(action)
        if actor_type:
            where_parts.append("actor_type = %s")
            params.append(actor_type)
        if actor_id:
            where_parts.append("actor_id = %s")
            params.append(actor_id)
        if start_time:
            where_parts.append("timestamp >= %s")
            params.append(start_time)
        if end_time:
            where_parts.append("timestamp <= %s")
            params.append(end_time)
        if correlation_id:
            where_parts.append("correlation_id = %s")
            params.append(correlation_id)

        where_clause = " AND ".join(where_parts)

        # Get total count
        count_result = await conn.execute(
            f"SELECT COUNT(*) FROM {SCHEMA_NAME}.provenance_events WHERE {where_clause}",
            params,
        )
        total = (await count_result.fetchone())[0]

        # Get page of events
        result = await conn.execute(
            f"""
            SELECT id, tenant_id, entity_type, entity_id, action, actor_type,
                   actor_id, actor_name, timestamp, reason, changes, metadata,
                   related_entity_type, related_entity_id, correlation_id,
                   request_id, created_at
            FROM {SCHEMA_NAME}.provenance_events
            WHERE {where_clause}
            ORDER BY timestamp DESC
            LIMIT %s OFFSET %s
            """,
            params + [page_size, offset],
        )
        rows = await result.fetchall()

    items = [_row_to_response(row) for row in rows]

    return ProvenanceEventListResponse(
        items=items, total=total, page=page, page_size=page_size
    )


async def get_correlated_events(
    tenant_id: int, correlation_id: str
) -> list[ProvenanceEventResponse]:
    """Get all events with the same correlation ID."""
    async with get_connection() as conn:
        result = await conn.execute(
            f"""
            SELECT id, tenant_id, entity_type, entity_id, action, actor_type,
                   actor_id, actor_name, timestamp, reason, changes, metadata,
                   related_entity_type, related_entity_id, correlation_id,
                   request_id, created_at
            FROM {SCHEMA_NAME}.provenance_events
            WHERE tenant_id = %s AND correlation_id = %s
            ORDER BY timestamp ASC
            """,
            (tenant_id, correlation_id),
        )
        rows = await result.fetchall()

    return [_row_to_response(row) for row in rows]
