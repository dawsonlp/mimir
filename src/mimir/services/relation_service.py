"""Relation service - database operations for relations (V2)."""

from psycopg.types.json import Json

from mimir.database import get_connection
from mimir.schemas.relation import (
    EntityType,
    RelationCreate,
    RelationListResponse,
    RelationQueryParams,
    RelationResponse,
    RelationUpdate,
)

SCHEMA_NAME = "mimirdata"


async def create_relation(tenant_id: int, data: RelationCreate) -> RelationResponse:
    """Create a new relation."""
    async with get_connection() as conn:
        result = await conn.execute(
            f"""
            INSERT INTO {SCHEMA_NAME}.relation
                (tenant_id, relation_type, source_entity_type, source_entity_id,
                 target_entity_type, target_entity_id, metadata)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id, tenant_id, relation_type, source_entity_type, source_entity_id,
                      target_entity_type, target_entity_id, metadata, created_at
            """,
            (
                tenant_id,
                data.relation_type,
                data.source_entity_type.value,
                data.source_entity_id,
                data.target_entity_type.value,
                data.target_entity_id,
                Json(data.metadata) if data.metadata else None,
            ),
        )
        row = await result.fetchone()
        await conn.commit()

    return _row_to_relation_response(row)


async def get_relation(relation_id: int, tenant_id: int) -> RelationResponse | None:
    """Get relation by ID."""
    async with get_connection() as conn:
        result = await conn.execute(
            f"""
            SELECT id, tenant_id, relation_type, source_entity_type, source_entity_id,
                   target_entity_type, target_entity_id, metadata, created_at
            FROM {SCHEMA_NAME}.relation
            WHERE id = %s AND tenant_id = %s
            """,
            (relation_id, tenant_id),
        )
        row = await result.fetchone()

    if not row:
        return None

    return _row_to_relation_response(row)


async def list_relations(
    tenant_id: int,
    params: RelationQueryParams | None = None,
) -> RelationListResponse:
    """List relations with optional filtering."""
    async with get_connection() as conn:
        where_clause = "WHERE tenant_id = %s"
        query_params: list = [tenant_id]

        if params:
            if params.source_entity_type:
                where_clause += " AND source_entity_type = %s"
                query_params.append(params.source_entity_type.value)
            if params.source_entity_id is not None:
                where_clause += " AND source_entity_id = %s"
                query_params.append(params.source_entity_id)
            if params.target_entity_type:
                where_clause += " AND target_entity_type = %s"
                query_params.append(params.target_entity_type.value)
            if params.target_entity_id is not None:
                where_clause += " AND target_entity_id = %s"
                query_params.append(params.target_entity_id)
            if params.relation_type:
                where_clause += " AND relation_type = %s"
                query_params.append(params.relation_type)

        # Get count
        count_result = await conn.execute(
            f"SELECT COUNT(*) FROM {SCHEMA_NAME}.relation {where_clause}",
            query_params,
        )
        total = (await count_result.fetchone())[0]

        # Get relations
        result = await conn.execute(
            f"""
            SELECT id, tenant_id, relation_type, source_entity_type, source_entity_id,
                   target_entity_type, target_entity_id, metadata, created_at
            FROM {SCHEMA_NAME}.relation
            {where_clause}
            ORDER BY created_at DESC
            """,
            query_params,
        )
        rows = await result.fetchall()

    items = [_row_to_relation_response(row) for row in rows]

    return RelationListResponse(items=items, total=total)


async def update_relation(
    relation_id: int, tenant_id: int, data: RelationUpdate
) -> RelationResponse | None:
    """Update a relation."""
    updates = []
    params = []

    if data.relation_type is not None:
        updates.append("relation_type = %s")
        params.append(data.relation_type)
    if data.metadata is not None:
        updates.append("metadata = %s")
        params.append(Json(data.metadata))

    if not updates:
        return await get_relation(relation_id, tenant_id)

    params.extend([relation_id, tenant_id])

    async with get_connection() as conn:
        result = await conn.execute(
            f"""
            UPDATE {SCHEMA_NAME}.relation
            SET {", ".join(updates)}
            WHERE id = %s AND tenant_id = %s
            RETURNING id, tenant_id, relation_type, source_entity_type, source_entity_id,
                      target_entity_type, target_entity_id, metadata, created_at
            """,
            params,
        )
        row = await result.fetchone()
        await conn.commit()

    if not row:
        return None

    return _row_to_relation_response(row)


async def delete_relation(relation_id: int, tenant_id: int) -> bool:
    """Delete a relation."""
    async with get_connection() as conn:
        result = await conn.execute(
            f"""
            DELETE FROM {SCHEMA_NAME}.relation
            WHERE id = %s AND tenant_id = %s
            RETURNING id
            """,
            (relation_id, tenant_id),
        )
        row = await result.fetchone()
        await conn.commit()

    return row is not None


async def get_entity_relations(
    tenant_id: int,
    entity_type: EntityType,
    entity_id: int,
    as_source: bool = True,
    as_target: bool = True,
    relation_type: str | None = None,
) -> list[RelationResponse]:
    """Get all relations for an entity (as source, target, or both)."""
    async with get_connection() as conn:
        conditions = ["tenant_id = %s"]
        params: list = [tenant_id]

        entity_conditions = []
        if as_source:
            entity_conditions.append(
                "(source_entity_type = %s AND source_entity_id = %s)"
            )
            params.extend([entity_type.value, entity_id])
        if as_target:
            entity_conditions.append(
                "(target_entity_type = %s AND target_entity_id = %s)"
            )
            params.extend([entity_type.value, entity_id])

        if entity_conditions:
            conditions.append(f"({' OR '.join(entity_conditions)})")

        if relation_type:
            conditions.append("relation_type = %s")
            params.append(relation_type)

        where_clause = " AND ".join(conditions)

        result = await conn.execute(
            f"""
            SELECT id, tenant_id, relation_type, source_entity_type, source_entity_id,
                   target_entity_type, target_entity_id, metadata, created_at
            FROM {SCHEMA_NAME}.relation
            WHERE {where_clause}
            ORDER BY created_at DESC
            """,
            params,
        )
        rows = await result.fetchall()

    return [_row_to_relation_response(row) for row in rows]


async def check_relation_exists(
    tenant_id: int,
    relation_type: str,
    source_entity_type: EntityType,
    source_entity_id: int,
    target_entity_type: EntityType,
    target_entity_id: int,
) -> bool:
    """Check if a specific relation already exists."""
    async with get_connection() as conn:
        result = await conn.execute(
            f"""
            SELECT 1 FROM {SCHEMA_NAME}.relation
            WHERE tenant_id = %s
              AND relation_type = %s
              AND source_entity_type = %s
              AND source_entity_id = %s
              AND target_entity_type = %s
              AND target_entity_id = %s
            """,
            (
                tenant_id,
                relation_type,
                source_entity_type.value,
                source_entity_id,
                target_entity_type.value,
                target_entity_id,
            ),
        )
        row = await result.fetchone()

    return row is not None


def _row_to_relation_response(row: tuple) -> RelationResponse:
    """Convert database row to RelationResponse."""
    return RelationResponse(
        id=row[0],
        tenant_id=row[1],
        relation_type=row[2],
        source_entity_type=EntityType(row[3]),
        source_entity_id=row[4],
        target_entity_type=EntityType(row[5]),
        target_entity_id=row[6],
        metadata=row[7],
        created_at=row[8],
    )
