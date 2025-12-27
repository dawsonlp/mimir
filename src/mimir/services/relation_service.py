"""Relation service - database operations for relations."""

from mimir.database import get_connection
from mimir.models import SCHEMA_NAME
from mimir.schemas.relation import (
    RelationCreate,
    RelationListResponse,
    RelationResponse,
    RelationUpdate,
)


async def create_relation(tenant_id: int, data: RelationCreate) -> RelationResponse:
    """Create a new relation."""
    async with get_connection() as conn:
        result = await conn.execute(
            f"""
            INSERT INTO {SCHEMA_NAME}.relations
                (tenant_id, source_type, source_id, target_type, target_id,
                 relation_type, description, confidence, metadata)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id, tenant_id, source_type, source_id, target_type, target_id,
                      relation_type, description, confidence, created_at, updated_at, metadata
            """,
            (
                tenant_id,
                data.source_type.value,
                data.source_id,
                data.target_type.value,
                data.target_id,
                data.relation_type.value,
                data.description,
                data.confidence,
                data.metadata,
            ),
        )
        row = await result.fetchone()
        await conn.commit()

    return RelationResponse(
        id=row[0],
        tenant_id=row[1],
        source_type=row[2],
        source_id=row[3],
        target_type=row[4],
        target_id=row[5],
        relation_type=row[6],
        description=row[7],
        confidence=row[8],
        created_at=row[9],
        updated_at=row[10],
        metadata=row[11],
    )


async def get_relation(relation_id: int, tenant_id: int) -> RelationResponse | None:
    """Get relation by ID."""
    async with get_connection() as conn:
        result = await conn.execute(
            f"""
            SELECT id, tenant_id, source_type, source_id, target_type, target_id,
                   relation_type, description, confidence, created_at, updated_at, metadata
            FROM {SCHEMA_NAME}.relations
            WHERE id = %s AND tenant_id = %s
            """,
            (relation_id, tenant_id),
        )
        row = await result.fetchone()

    if not row:
        return None

    return RelationResponse(
        id=row[0],
        tenant_id=row[1],
        source_type=row[2],
        source_id=row[3],
        target_type=row[4],
        target_id=row[5],
        relation_type=row[6],
        description=row[7],
        confidence=row[8],
        created_at=row[9],
        updated_at=row[10],
        metadata=row[11],
    )


async def list_relations(
    tenant_id: int,
    page: int = 1,
    page_size: int = 20,
    source_type: str | None = None,
    source_id: int | None = None,
    target_type: str | None = None,
    target_id: int | None = None,
    relation_type: str | None = None,
) -> RelationListResponse:
    """List relations for a tenant with pagination and filtering."""
    offset = (page - 1) * page_size

    async with get_connection() as conn:
        # Build query with optional filters
        where_clause = "WHERE tenant_id = %s"
        params: list = [tenant_id]

        if source_type:
            where_clause += " AND source_type = %s"
            params.append(source_type)
        if source_id is not None:
            where_clause += " AND source_id = %s"
            params.append(source_id)
        if target_type:
            where_clause += " AND target_type = %s"
            params.append(target_type)
        if target_id is not None:
            where_clause += " AND target_id = %s"
            params.append(target_id)
        if relation_type:
            where_clause += " AND relation_type = %s"
            params.append(relation_type)

        # Get total count
        count_result = await conn.execute(
            f"SELECT COUNT(*) FROM {SCHEMA_NAME}.relations {where_clause}",
            params,
        )
        total = (await count_result.fetchone())[0]

        # Get page of relations
        result = await conn.execute(
            f"""
            SELECT id, tenant_id, source_type, source_id, target_type, target_id,
                   relation_type, description, confidence, created_at, updated_at, metadata
            FROM {SCHEMA_NAME}.relations
            {where_clause}
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
            """,
            params + [page_size, offset],
        )
        rows = await result.fetchall()

    items = [
        RelationResponse(
            id=row[0],
            tenant_id=row[1],
            source_type=row[2],
            source_id=row[3],
            target_type=row[4],
            target_id=row[5],
            relation_type=row[6],
            description=row[7],
            confidence=row[8],
            created_at=row[9],
            updated_at=row[10],
            metadata=row[11],
        )
        for row in rows
    ]

    return RelationListResponse(
        items=items, total=total, page=page, page_size=page_size
    )


async def list_entity_relations(
    tenant_id: int,
    entity_type: str,
    entity_id: int,
    page: int = 1,
    page_size: int = 20,
) -> RelationListResponse:
    """List all relations involving an entity (as source or target)."""
    offset = (page - 1) * page_size

    async with get_connection() as conn:
        # Get total count for entity as source or target
        count_result = await conn.execute(
            f"""
            SELECT COUNT(*) FROM {SCHEMA_NAME}.relations
            WHERE tenant_id = %s
              AND ((source_type = %s AND source_id = %s)
                   OR (target_type = %s AND target_id = %s))
            """,
            (tenant_id, entity_type, entity_id, entity_type, entity_id),
        )
        total = (await count_result.fetchone())[0]

        # Get page of relations
        result = await conn.execute(
            f"""
            SELECT id, tenant_id, source_type, source_id, target_type, target_id,
                   relation_type, description, confidence, created_at, updated_at, metadata
            FROM {SCHEMA_NAME}.relations
            WHERE tenant_id = %s
              AND ((source_type = %s AND source_id = %s)
                   OR (target_type = %s AND target_id = %s))
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
            """,
            (tenant_id, entity_type, entity_id, entity_type, entity_id, page_size, offset),
        )
        rows = await result.fetchall()

    items = [
        RelationResponse(
            id=row[0],
            tenant_id=row[1],
            source_type=row[2],
            source_id=row[3],
            target_type=row[4],
            target_id=row[5],
            relation_type=row[6],
            description=row[7],
            confidence=row[8],
            created_at=row[9],
            updated_at=row[10],
            metadata=row[11],
        )
        for row in rows
    ]

    return RelationListResponse(
        items=items, total=total, page=page, page_size=page_size
    )


async def update_relation(
    relation_id: int, tenant_id: int, data: RelationUpdate
) -> RelationResponse | None:
    """Update relation."""
    updates = []
    params = []

    if data.relation_type is not None:
        updates.append("relation_type = %s")
        params.append(data.relation_type.value)
    if data.description is not None:
        updates.append("description = %s")
        params.append(data.description)
    if data.confidence is not None:
        updates.append("confidence = %s")
        params.append(data.confidence)
    if data.metadata is not None:
        updates.append("metadata = %s")
        params.append(data.metadata)

    if not updates:
        return await get_relation(relation_id, tenant_id)

    params.extend([relation_id, tenant_id])

    async with get_connection() as conn:
        result = await conn.execute(
            f"""
            UPDATE {SCHEMA_NAME}.relations
            SET {", ".join(updates)}
            WHERE id = %s AND tenant_id = %s
            RETURNING id, tenant_id, source_type, source_id, target_type, target_id,
                      relation_type, description, confidence, created_at, updated_at, metadata
            """,
            params,
        )
        row = await result.fetchone()
        await conn.commit()

    if not row:
        return None

    return RelationResponse(
        id=row[0],
        tenant_id=row[1],
        source_type=row[2],
        source_id=row[3],
        target_type=row[4],
        target_id=row[5],
        relation_type=row[6],
        description=row[7],
        confidence=row[8],
        created_at=row[9],
        updated_at=row[10],
        metadata=row[11],
    )


async def delete_relation(relation_id: int, tenant_id: int) -> bool:
    """Delete a relation."""
    async with get_connection() as conn:
        result = await conn.execute(
            f"""
            DELETE FROM {SCHEMA_NAME}.relations
            WHERE id = %s AND tenant_id = %s
            RETURNING id
            """,
            (relation_id, tenant_id),
        )
        row = await result.fetchone()
        await conn.commit()

    return row is not None
