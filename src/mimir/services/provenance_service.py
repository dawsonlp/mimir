"""Provenance service - database operations for audit log (V2)."""

from datetime import datetime

from psycopg.types.json import Json

from mimir.database import get_connection
from mimir.schemas.provenance import (
    ProvenanceAction,
    ProvenanceActorType,
    ProvenanceEventCreate,
    ProvenanceEventListResponse,
    ProvenanceEventResponse,
    ProvenanceQueryParams,
)
from mimir.schemas.relation import EntityType

SCHEMA_NAME = "mimirdata"


async def create_provenance_event(
    tenant_id: int, data: ProvenanceEventCreate
) -> ProvenanceEventResponse:
    """Create a new provenance event."""
    async with get_connection() as conn:
        result = await conn.execute(
            f"""
            INSERT INTO {SCHEMA_NAME}.provenance_event
                (tenant_id, entity_type, entity_id, action, actor_type, actor_id,
                 reason, before_state, after_state, metadata)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id, tenant_id, entity_type, entity_id, action, actor_type, actor_id,
                      reason, before_state, after_state, metadata, created_at
            """,
            (
                tenant_id,
                data.entity_type.value,
                data.entity_id,
                data.action.value,
                data.actor_type.value,
                data.actor_id,
                data.reason,
                Json(data.before_state) if data.before_state else None,
                Json(data.after_state) if data.after_state else None,
                Json(data.metadata) if data.metadata else None,
            ),
        )
        row = await result.fetchone()
        await conn.commit()

    return _row_to_provenance_response(row)


async def get_provenance_event(
    event_id: int, tenant_id: int
) -> ProvenanceEventResponse | None:
    """Get provenance event by ID."""
    async with get_connection() as conn:
        result = await conn.execute(
            f"""
            SELECT id, tenant_id, entity_type, entity_id, action, actor_type, actor_id,
                   reason, before_state, after_state, metadata, created_at
            FROM {SCHEMA_NAME}.provenance_event
            WHERE id = %s AND tenant_id = %s
            """,
            (event_id, tenant_id),
        )
        row = await result.fetchone()

    if not row:
        return None

    return _row_to_provenance_response(row)


async def list_provenance_events(
    tenant_id: int,
    params: ProvenanceQueryParams | None = None,
    limit: int = 100,
    offset: int = 0,
) -> ProvenanceEventListResponse:
    """List provenance events with optional filtering."""
    async with get_connection() as conn:
        where_clause = "WHERE tenant_id = %s"
        query_params: list = [tenant_id]

        if params:
            if params.entity_type:
                where_clause += " AND entity_type = %s"
                query_params.append(params.entity_type.value)
            if params.entity_id is not None:
                where_clause += " AND entity_id = %s"
                query_params.append(params.entity_id)
            if params.action:
                where_clause += " AND action = %s"
                query_params.append(params.action.value)
            if params.actor_type:
                where_clause += " AND actor_type = %s"
                query_params.append(params.actor_type.value)
            if params.actor_id:
                where_clause += " AND actor_id = %s"
                query_params.append(params.actor_id)
            if params.since:
                where_clause += " AND created_at >= %s"
                query_params.append(params.since)
            if params.until:
                where_clause += " AND created_at <= %s"
                query_params.append(params.until)

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
                   reason, before_state, after_state, metadata, created_at
            FROM {SCHEMA_NAME}.provenance_event
            {where_clause}
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
            """,
            query_params + [limit, offset],
        )
        rows = await result.fetchall()

    items = [_row_to_provenance_response(row) for row in rows]

    return ProvenanceEventListResponse(items=items, total=total)


async def get_entity_history(
    tenant_id: int,
    entity_type: EntityType,
    entity_id: int,
) -> list[ProvenanceEventResponse]:
    """Get full history for a specific entity."""
    async with get_connection() as conn:
        result = await conn.execute(
            f"""
            SELECT id, tenant_id, entity_type, entity_id, action, actor_type, actor_id,
                   reason, before_state, after_state, metadata, created_at
            FROM {SCHEMA_NAME}.provenance_event
            WHERE tenant_id = %s AND entity_type = %s AND entity_id = %s
            ORDER BY created_at ASC
            """,
            (tenant_id, entity_type.value, entity_id),
        )
        rows = await result.fetchall()

    return [_row_to_provenance_response(row) for row in rows]


async def get_actor_activity(
    tenant_id: int,
    actor_type: ProvenanceActorType,
    actor_id: str,
    since: datetime | None = None,
    until: datetime | None = None,
) -> list[ProvenanceEventResponse]:
    """Get all activity by a specific actor."""
    async with get_connection() as conn:
        where_clause = "WHERE tenant_id = %s AND actor_type = %s AND actor_id = %s"
        params: list = [tenant_id, actor_type.value, actor_id]

        if since:
            where_clause += " AND created_at >= %s"
            params.append(since)
        if until:
            where_clause += " AND created_at <= %s"
            params.append(until)

        result = await conn.execute(
            f"""
            SELECT id, tenant_id, entity_type, entity_id, action, actor_type, actor_id,
                   reason, before_state, after_state, metadata, created_at
            FROM {SCHEMA_NAME}.provenance_event
            {where_clause}
            ORDER BY created_at DESC
            """,
            params,
        )
        rows = await result.fetchall()

    return [_row_to_provenance_response(row) for row in rows]


# Helper function to log provenance automatically
async def log_action(
    tenant_id: int,
    entity_type: EntityType,
    entity_id: int,
    action: ProvenanceAction,
    actor_type: ProvenanceActorType = ProvenanceActorType.SYSTEM,
    actor_id: str | None = None,
    reason: str | None = None,
    before_state: dict | None = None,
    after_state: dict | None = None,
    metadata: dict | None = None,
) -> ProvenanceEventResponse:
    """Convenience function to log a provenance event."""
    data = ProvenanceEventCreate(
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        actor_type=actor_type,
        actor_id=actor_id,
        reason=reason,
        before_state=before_state,
        after_state=after_state,
        metadata=metadata,
    )
    return await create_provenance_event(tenant_id, data)


def _row_to_provenance_response(row: tuple) -> ProvenanceEventResponse:
    """Convert database row to ProvenanceEventResponse."""
    return ProvenanceEventResponse(
        id=row[0],
        tenant_id=row[1],
        entity_type=EntityType(row[2]),
        entity_id=row[3],
        action=ProvenanceAction(row[4]),
        actor_type=ProvenanceActorType(row[5]),
        actor_id=row[6],
        reason=row[7],
        before_state=row[8],
        after_state=row[9],
        metadata=row[10],
        created_at=row[11],
    )
