"""Provenance service - database operations for audit log (V2 append-only).

V2 Changes:
- UUID primary keys
- UUID entity references
- Simplified - TEXT fields instead of enums
- Only 'create' action for now (append-only system)
- Events are auto-created, not via API
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from psycopg.types.json import Json

from mimir.database import get_connection
from mimir.ids import new_uuid7
from mimir.schemas.provenance import (
    ProvenanceEventListResponse,
    ProvenanceEventResponse,
)

SCHEMA_NAME = "mimirdata"


async def log_action(
    tenant_id: int,
    entity_type: str,
    entity_id: UUID,
    action: str = "create",
    actor_type: str = "api_client",
    actor_id: str | None = None,
    reason: str | None = None,
    metadata: dict | None = None,
    conn: Any | None = None,
) -> ProvenanceEventResponse:
    """Log a provenance event (internal use - not exposed via API)."""
    event_id = new_uuid7()

    if conn is not None:
        return await _insert_provenance_event(
            conn=conn,
            event_id=event_id,
            tenant_id=tenant_id,
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            actor_type=actor_type,
            actor_id=actor_id,
            reason=reason,
            metadata=metadata,
        )

    async with get_connection() as conn:
        event = await _insert_provenance_event(
            conn=conn,
            event_id=event_id,
            tenant_id=tenant_id,
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            actor_type=actor_type,
            actor_id=actor_id,
            reason=reason,
            metadata=metadata,
        )
        await conn.commit()

    return event


async def _insert_provenance_event(
    *,
    conn: Any,
    event_id: UUID,
    tenant_id: int,
    entity_type: str,
    entity_id: UUID,
    action: str,
    actor_type: str,
    actor_id: str | None,
    reason: str | None,
    metadata: dict | None,
) -> ProvenanceEventResponse:
    result = await conn.execute(
        f"""
        INSERT INTO {SCHEMA_NAME}.provenance_event
            (id, tenant_id, entity_type, entity_id, action, actor_type, actor_id,
             reason, metadata)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id, tenant_id, entity_type, entity_id, action, actor_type, actor_id,
                  reason, metadata, created_at
        """,
        (
            str(event_id),
            tenant_id,
            entity_type,
            str(entity_id),
            action,
            actor_type,
            actor_id,
            reason,
            Json(metadata) if metadata else None,
        ),
    )
    row = await result.fetchone()
    return _row_to_provenance_response(row)


async def get_provenance_event(
    event_id: UUID, tenant_id: int
) -> ProvenanceEventResponse | None:
    """Get provenance event by UUID."""
    async with get_connection() as conn:
        result = await conn.execute(
            f"""
            SELECT id, tenant_id, entity_type, entity_id, action, actor_type, actor_id,
                   reason, metadata, created_at
            FROM {SCHEMA_NAME}.provenance_event
            WHERE id = %s AND tenant_id = %s
            """,
            (str(event_id), tenant_id),
        )
        row = await result.fetchone()

    if not row:
        return None

    return _row_to_provenance_response(row)


async def list_provenance_events(
    tenant_id: int,
    limit: int = 50,
    offset: int = 0,
    entity_type: str | None = None,
    entity_id: UUID | None = None,
    action: str | None = None,
    actor_type: str | None = None,
    actor_id: str | None = None,
    after: datetime | None = None,
    before: datetime | None = None,
) -> ProvenanceEventListResponse:
    """List provenance events with optional filtering."""
    async with get_connection() as conn:
        where_clause = "WHERE tenant_id = %s"
        query_params: list = [tenant_id]

        if entity_type:
            where_clause += " AND entity_type = %s"
            query_params.append(entity_type)
        if entity_id:
            where_clause += " AND entity_id = %s"
            query_params.append(str(entity_id))
        if action:
            where_clause += " AND action = %s"
            query_params.append(action)
        if actor_type:
            where_clause += " AND actor_type = %s"
            query_params.append(actor_type)
        if actor_id:
            where_clause += " AND actor_id = %s"
            query_params.append(actor_id)
        if after:
            where_clause += " AND created_at >= %s"
            query_params.append(after)
        if before:
            where_clause += " AND created_at <= %s"
            query_params.append(before)

        # Get count
        count_result = await conn.execute(
            f"SELECT COUNT(*) FROM {SCHEMA_NAME}.provenance_event {where_clause}",
            query_params,
        )
        total = (await count_result.fetchone())[0]

        # Get events
        result = await conn.execute(
            f"""
            SELECT id, tenant_id, entity_type, entity_id, action, actor_type, actor_id,
                   reason, metadata, created_at
            FROM {SCHEMA_NAME}.provenance_event
            {where_clause}
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
            """,
            query_params + [limit, offset],
        )
        rows = await result.fetchall()

    items = [_row_to_provenance_response(row) for row in rows]

    return ProvenanceEventListResponse(
        items=items, total=total, limit=limit, offset=offset
    )


async def get_artifact_history(
    tenant_id: int,
    artifact_id: UUID,
) -> list[ProvenanceEventResponse]:
    """Get full history for a specific artifact."""
    async with get_connection() as conn:
        result = await conn.execute(
            f"""
            SELECT id, tenant_id, entity_type, entity_id, action, actor_type, actor_id,
                   reason, metadata, created_at
            FROM {SCHEMA_NAME}.provenance_event
            WHERE tenant_id = %s AND entity_type = 'artifact' AND entity_id = %s
            ORDER BY created_at ASC
            """,
            (tenant_id, str(artifact_id)),
        )
        rows = await result.fetchall()

    return [_row_to_provenance_response(row) for row in rows]


def _row_to_provenance_response(row: tuple) -> ProvenanceEventResponse:
    """Convert database row to ProvenanceEventResponse."""
    return ProvenanceEventResponse(
        id=UUID(row[0]) if isinstance(row[0], str) else row[0],
        tenant_id=row[1],
        entity_type=row[2],
        entity_id=UUID(row[3]) if isinstance(row[3], str) else row[3],
        action=row[4],
        actor_type=row[5],
        actor_id=row[6],
        reason=row[7],
        metadata=row[8],
        created_at=row[9],
    )


# NOTE: create_provenance_event via API removed - events are auto-created
