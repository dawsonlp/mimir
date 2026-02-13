"""Relation service - database operations for relations (V2.2 with soft-delete awareness).

V2.2 Changes (Phase 2):
- All retrieval queries join artifact table to exclude relations where
  source OR target artifact is soft-deleted (deleted_at IS NOT NULL)

V2 Changes:
- UUID primary keys (client-generated or server-generated)
- UUID references to artifacts (not INT)
- Simplified - only connects artifacts (no entity_type enum)
- Append-only: no update or delete operations
- Returns 409 Conflict on duplicate relation
"""

from uuid import UUID, uuid4

from psycopg import errors as pg_errors
from psycopg.types.json import Json

from mimir.database import get_connection
from mimir.schemas.relation import (
    RelationCreate,
    RelationListResponse,
    RelationResponse,
)
from mimir.services import provenance_service

SCHEMA_NAME = "mimirdata"


async def create_relation(tenant_id: int, data: RelationCreate) -> RelationResponse | None:
    """Create a new relation.
    
    If data.id is provided, uses that UUID. Otherwise generates one.
    Returns None if duplicate relation exists (caller should return 409).
    """
    # Use client-provided UUID or generate one
    relation_id = data.id if data.id else uuid4()

    async with get_connection() as conn:
        try:
            result = await conn.execute(
                f"""
                INSERT INTO {SCHEMA_NAME}.relation
                    (id, tenant_id, source_id, target_id, relation_type,
                     confidence, metadata)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id, tenant_id, source_id, target_id, relation_type,
                          confidence, metadata, created_at
                """,
                (
                    str(relation_id),
                    tenant_id,
                    str(data.source_id),
                    str(data.target_id),
                    data.relation_type,
                    data.confidence,
                    Json(data.metadata) if data.metadata else None,
                ),
            )
            row = await result.fetchone()
            await conn.commit()
        except pg_errors.UniqueViolation:
            # Duplicate relation - return None to signal 409
            await conn.rollback()
            return None

    relation = _row_to_relation_response(row)

    # Log provenance event
    await provenance_service.log_action(
        tenant_id=tenant_id,
        entity_type="relation",
        entity_id=relation.id,
        action="create",
        actor_type="api_client",
        metadata={
            "relation_type": relation.relation_type,
            "source_id": str(relation.source_id),
            "target_id": str(relation.target_id),
        },
    )

    return relation


async def get_relation(relation_id: UUID, tenant_id: int) -> RelationResponse | None:
    """Get relation by UUID. Excludes relations where source or target is soft-deleted."""
    async with get_connection() as conn:
        result = await conn.execute(
            f"""
            SELECT r.id, r.tenant_id, r.source_id, r.target_id, r.relation_type,
                   r.confidence, r.metadata, r.created_at
            FROM {SCHEMA_NAME}.relation r
            JOIN {SCHEMA_NAME}.artifact src ON src.id = r.source_id
            JOIN {SCHEMA_NAME}.artifact tgt ON tgt.id = r.target_id
            WHERE r.id = %s AND r.tenant_id = %s
              AND src.deleted_at IS NULL AND tgt.deleted_at IS NULL
            """,
            (str(relation_id), tenant_id),
        )
        row = await result.fetchone()

    if not row:
        return None

    return _row_to_relation_response(row)


async def list_relations(
    tenant_id: int,
    limit: int = 50,
    offset: int = 0,
    source_id: UUID | None = None,
    target_id: UUID | None = None,
    relation_type: str | None = None,
) -> RelationListResponse:
    """List relations with optional filtering. Excludes relations with soft-deleted endpoints."""
    async with get_connection() as conn:
        where_clause = "WHERE r.tenant_id = %s AND src.deleted_at IS NULL AND tgt.deleted_at IS NULL"
        query_params: list = [tenant_id]

        if source_id:
            where_clause += " AND r.source_id = %s"
            query_params.append(str(source_id))
        if target_id:
            where_clause += " AND r.target_id = %s"
            query_params.append(str(target_id))
        if relation_type:
            where_clause += " AND r.relation_type = %s"
            query_params.append(relation_type)

        join_clause = f"""
            FROM {SCHEMA_NAME}.relation r
            JOIN {SCHEMA_NAME}.artifact src ON src.id = r.source_id
            JOIN {SCHEMA_NAME}.artifact tgt ON tgt.id = r.target_id
        """

        # Get count
        count_result = await conn.execute(
            f"SELECT COUNT(*) {join_clause} {where_clause}",
            query_params,
        )
        total = (await count_result.fetchone())[0]

        # Get relations
        result = await conn.execute(
            f"""
            SELECT r.id, r.tenant_id, r.source_id, r.target_id, r.relation_type,
                   r.confidence, r.metadata, r.created_at
            {join_clause}
            {where_clause}
            ORDER BY r.created_at DESC
            LIMIT %s OFFSET %s
            """,
            query_params + [limit, offset],
        )
        rows = await result.fetchall()

    items = [_row_to_relation_response(row) for row in rows]

    return RelationListResponse(items=items, total=total, limit=limit, offset=offset)


async def get_artifact_relations(
    tenant_id: int,
    artifact_id: UUID,
    as_source: bool = True,
    as_target: bool = True,
    relation_type: str | None = None,
) -> list[RelationResponse]:
    """Get all relations for an artifact (as source, target, or both).

    Excludes relations where the other endpoint artifact is soft-deleted.
    """
    async with get_connection() as conn:
        conditions = ["r.tenant_id = %s", "src.deleted_at IS NULL", "tgt.deleted_at IS NULL"]
        params: list = [tenant_id]

        entity_conditions = []
        if as_source:
            entity_conditions.append("r.source_id = %s")
            params.append(str(artifact_id))
        if as_target:
            entity_conditions.append("r.target_id = %s")
            params.append(str(artifact_id))

        if entity_conditions:
            conditions.append(f"({' OR '.join(entity_conditions)})")

        if relation_type:
            conditions.append("r.relation_type = %s")
            params.append(relation_type)

        where_clause = " AND ".join(conditions)

        result = await conn.execute(
            f"""
            SELECT r.id, r.tenant_id, r.source_id, r.target_id, r.relation_type,
                   r.confidence, r.metadata, r.created_at
            FROM {SCHEMA_NAME}.relation r
            JOIN {SCHEMA_NAME}.artifact src ON src.id = r.source_id
            JOIN {SCHEMA_NAME}.artifact tgt ON tgt.id = r.target_id
            WHERE {where_clause}
            ORDER BY r.created_at DESC
            """,
            params,
        )
        rows = await result.fetchall()

    return [_row_to_relation_response(row) for row in rows]


async def check_relation_exists(
    tenant_id: int,
    relation_type: str,
    source_id: UUID,
    target_id: UUID,
) -> bool:
    """Check if a specific relation already exists (ignores soft-delete status)."""
    async with get_connection() as conn:
        result = await conn.execute(
            f"""
            SELECT 1 FROM {SCHEMA_NAME}.relation
            WHERE tenant_id = %s
              AND relation_type = %s
              AND source_id = %s
              AND target_id = %s
            """,
            (tenant_id, relation_type, str(source_id), str(target_id)),
        )
        row = await result.fetchone()

    return row is not None


def _row_to_relation_response(row: tuple) -> RelationResponse:
    """Convert database row to RelationResponse."""
    return RelationResponse(
        id=UUID(row[0]) if isinstance(row[0], str) else row[0],
        tenant_id=row[1],
        source_id=UUID(row[2]) if isinstance(row[2], str) else row[2],
        target_id=UUID(row[3]) if isinstance(row[3], str) else row[3],
        relation_type=row[4],
        confidence=row[5],
        metadata=row[6],
        created_at=row[7],
    )


# NOTE: update_relation and delete_relation removed - relations are append-only
