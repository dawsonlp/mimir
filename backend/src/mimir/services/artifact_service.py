"""Artifact service - database operations for artifacts (V2.2 with deletion).

V2.2 Changes (Phase 2):
- Soft-delete: sets deleted_at timestamp, cascade via parent_artifact_id
- Physical-delete: removes rows from all tables (FK-safe ordering)
- All retrieval queries filter deleted_at IS NULL by default
- include_deleted flag for administrative access

V2 Changes:
- UUID primary keys (client-generated or server-generated)
- Append-only: no update operations
- Returns 409 Conflict on duplicate UUID
"""

import hashlib
from datetime import datetime
from uuid import UUID, uuid4

from psycopg import errors as pg_errors
from psycopg.types.json import Json

from mimir.database import get_connection
from mimir.schemas.artifact import (
    ArtifactCreate,
    ArtifactListResponse,
    ArtifactResponse,
    PhysicalDeleteResponse,
    SoftDeleteResponse,
)
from mimir.services import provenance_service

SCHEMA_NAME = "mimirdata"
VECTOR_SCHEMA = "mimir_vectors"

# Standard SELECT columns for artifact (16 columns with deleted_at)
_ARTIFACT_COLUMNS = """
    id, tenant_id, artifact_type, parent_artifact_id,
    start_offset, end_offset, position_metadata,
    title, content, content_hash,
    source, source_system, external_id, metadata,
    created_at, deleted_at
"""


def _hash_content(content: str | None) -> str | None:
    """Generate SHA-256 hash of content."""
    if content is None:
        return None
    return hashlib.sha256(content.encode()).hexdigest()


async def create_artifact(tenant_id: int, data: ArtifactCreate) -> ArtifactResponse | None:
    """Create a new artifact.

    If data.id is provided, uses that UUID. Otherwise generates one.
    Returns None if UUID already exists (caller should return 409).
    """
    content_hash = _hash_content(data.content)

    # Use client-provided UUID or generate one
    artifact_id = data.id if data.id else uuid4()

    async with get_connection() as conn:
        try:
            result = await conn.execute(
                f"""
                INSERT INTO {SCHEMA_NAME}.artifact
                    (id, tenant_id, artifact_type, parent_artifact_id,
                     start_offset, end_offset, position_metadata,
                     title, content, content_hash,
                     source, source_system, external_id, metadata)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING {_ARTIFACT_COLUMNS}
                """,
                (
                    str(artifact_id),
                    tenant_id,
                    data.artifact_type,
                    str(data.parent_artifact_id) if data.parent_artifact_id else None,
                    data.start_offset,
                    data.end_offset,
                    Json(data.position_metadata) if data.position_metadata else None,
                    data.title,
                    data.content,
                    content_hash,
                    data.source,
                    data.source_system,
                    data.external_id,
                    Json(data.metadata) if data.metadata else None,
                ),
            )
            row = await result.fetchone()
            await conn.commit()
        except pg_errors.UniqueViolation:
            # Duplicate UUID - return None to signal 409
            await conn.rollback()
            return None

    artifact = _row_to_artifact_response(row)

    # Log provenance event
    await provenance_service.log_action(
        tenant_id=tenant_id,
        entity_type="artifact",
        entity_id=artifact.id,
        action="create",
        actor_type="api_client",
        metadata={"title": artifact.title, "artifact_type": artifact.artifact_type},
    )

    return artifact


async def get_artifact(
    artifact_id: UUID,
    tenant_id: int,
    include_deleted: bool = False,
) -> ArtifactResponse | None:
    """Get artifact by UUID.

    By default excludes soft-deleted artifacts (returns None / 404).
    Set include_deleted=True for administrative access.
    """
    deleted_filter = "" if include_deleted else " AND deleted_at IS NULL"

    async with get_connection() as conn:
        result = await conn.execute(
            f"""
            SELECT {_ARTIFACT_COLUMNS}
            FROM {SCHEMA_NAME}.artifact
            WHERE id = %s AND tenant_id = %s{deleted_filter}
            """,
            (str(artifact_id), tenant_id),
        )
        row = await result.fetchone()

    if not row:
        return None

    return _row_to_artifact_response(row)


async def get_artifact_by_external_id(
    tenant_id: int, source_system: str, external_id: str
) -> ArtifactResponse | None:
    """Get artifact by external ID (excludes soft-deleted)."""
    async with get_connection() as conn:
        result = await conn.execute(
            f"""
            SELECT {_ARTIFACT_COLUMNS}
            FROM {SCHEMA_NAME}.artifact
            WHERE tenant_id = %s AND source_system = %s AND external_id = %s
              AND deleted_at IS NULL
            """,
            (tenant_id, source_system, external_id),
        )
        row = await result.fetchone()

    if not row:
        return None

    return _row_to_artifact_response(row)


async def list_artifacts(
    tenant_id: int,
    limit: int = 50,
    offset: int = 0,
    artifact_type: str | None = None,
    parent_artifact_id: UUID | None = None,
    content_hash: str | None = None,
    ids: list[UUID] | None = None,
    include_deleted: bool = False,
) -> ArtifactListResponse:
    """List artifacts for a tenant with pagination or batch retrieval.

    When `ids` is provided, retrieves specific artifacts by UUID (batch mode).
    Batch mode ignores pagination parameters and returns artifacts in the
    order of requested IDs.

    By default excludes soft-deleted artifacts.
    """
    # Batch retrieval mode
    if ids is not None:
        return await _get_artifacts_by_ids(tenant_id, ids, include_deleted)

    # Standard pagination mode
    deleted_filter = "" if include_deleted else " AND deleted_at IS NULL"

    async with get_connection() as conn:
        where_clause = f"WHERE tenant_id = %s{deleted_filter}"
        params: list = [tenant_id]

        if artifact_type:
            where_clause += " AND artifact_type = %s"
            params.append(artifact_type)
        if parent_artifact_id is not None:
            where_clause += " AND parent_artifact_id = %s"
            params.append(str(parent_artifact_id))
        if content_hash:
            where_clause += " AND content_hash = %s"
            params.append(content_hash)

        # Get total count
        count_result = await conn.execute(
            f"SELECT COUNT(*) FROM {SCHEMA_NAME}.artifact {where_clause}",
            params,
        )
        total = (await count_result.fetchone())[0]

        # Get page
        result = await conn.execute(
            f"""
            SELECT {_ARTIFACT_COLUMNS}
            FROM {SCHEMA_NAME}.artifact
            {where_clause}
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
            """,
            params + [limit, offset],
        )
        rows = await result.fetchall()

    items = [_row_to_artifact_response(row) for row in rows]

    return ArtifactListResponse(
        items=items, total=total, limit=limit, offset=offset
    )


async def _get_artifacts_by_ids(
    tenant_id: int, ids: list[UUID], include_deleted: bool = False
) -> ArtifactListResponse:
    """Retrieve artifacts by UUIDs, preserving request order.

    Uses PostgreSQL ANY() for efficient batch lookup.
    Missing IDs are silently omitted from results.
    """
    if not ids:
        return ArtifactListResponse(items=[], total=0, limit=0, offset=0)

    deleted_filter = "" if include_deleted else " AND deleted_at IS NULL"

    # Convert UUIDs to strings for query
    id_strings = [str(id) for id in ids]

    async with get_connection() as conn:
        result = await conn.execute(
            f"""
            SELECT {_ARTIFACT_COLUMNS}
            FROM {SCHEMA_NAME}.artifact
            WHERE tenant_id = %s AND id = ANY(%s){deleted_filter}
            """,
            (tenant_id, id_strings),
        )
        rows = await result.fetchall()

    # Build lookup by ID for ordering
    artifacts_by_id = {
        (UUID(row[0]) if isinstance(row[0], str) else row[0]): _row_to_artifact_response(row)
        for row in rows
    }

    # Return in requested order, omitting missing IDs
    items = [artifacts_by_id[id] for id in ids if id in artifacts_by_id]

    return ArtifactListResponse(
        items=items,
        total=len(items),
        limit=len(ids),  # Original request size
        offset=0,
    )


async def get_children(
    artifact_id: UUID, tenant_id: int, include_deleted: bool = False
) -> list[ArtifactResponse]:
    """Get all child artifacts (for positional types). Excludes soft-deleted by default."""
    deleted_filter = "" if include_deleted else " AND deleted_at IS NULL"

    async with get_connection() as conn:
        result = await conn.execute(
            f"""
            SELECT {_ARTIFACT_COLUMNS}
            FROM {SCHEMA_NAME}.artifact
            WHERE parent_artifact_id = %s AND tenant_id = %s{deleted_filter}
            ORDER BY start_offset NULLS LAST, created_at
            """,
            (str(artifact_id), tenant_id),
        )
        rows = await result.fetchall()

    return [_row_to_artifact_response(row) for row in rows]


# =============================================================================
# Soft Deletion (Phase 2, Item 6)
# =============================================================================


async def soft_delete_artifact(
    artifact_id: UUID,
    tenant_id: int,
    cascade: bool = True,
) -> SoftDeleteResponse | None:
    """Soft-delete an artifact by setting deleted_at = now().

    If cascade=True (default), all descendants via parent_artifact_id are
    also soft-deleted with the same timestamp.

    Returns None if the artifact does not exist or is already deleted.
    Raises ValueError with "has_children" if cascade=False and active children exist.
    """
    async with get_connection() as conn:
        # Verify artifact exists and is not already deleted
        check = await conn.execute(
            f"""
            SELECT id FROM {SCHEMA_NAME}.artifact
            WHERE id = %s AND tenant_id = %s AND deleted_at IS NULL
            """,
            (str(artifact_id), tenant_id),
        )
        if not await check.fetchone():
            return None

        if not cascade:
            # Check for active children
            children_check = await conn.execute(
                f"""
                SELECT COUNT(*) FROM {SCHEMA_NAME}.artifact
                WHERE parent_artifact_id = %s AND tenant_id = %s AND deleted_at IS NULL
                """,
                (str(artifact_id), tenant_id),
            )
            child_count = (await children_check.fetchone())[0]
            if child_count > 0:
                raise ValueError("has_children")

        # Recursive CTE to find all descendants (including the target itself)
        # Then UPDATE all of them in a single statement
        result = await conn.execute(
            f"""
            WITH RECURSIVE descendants AS (
                SELECT id
                FROM {SCHEMA_NAME}.artifact
                WHERE id = %s AND tenant_id = %s AND deleted_at IS NULL

                UNION ALL

                SELECT a.id
                FROM {SCHEMA_NAME}.artifact a
                INNER JOIN descendants d ON a.parent_artifact_id = d.id
                WHERE a.tenant_id = %s AND a.deleted_at IS NULL
            )
            UPDATE {SCHEMA_NAME}.artifact
            SET deleted_at = now()
            WHERE id IN (SELECT id FROM descendants)
            RETURNING id, deleted_at
            """,
            (str(artifact_id), tenant_id, tenant_id),
        )
        rows = await result.fetchall()
        await conn.commit()

    if not rows:
        return None

    deleted_ids = [UUID(row[0]) if isinstance(row[0], str) else row[0] for row in rows]
    deleted_at = rows[0][1]

    # Log provenance event
    await provenance_service.log_action(
        tenant_id=tenant_id,
        entity_type="artifact",
        entity_id=artifact_id,
        action="soft_delete",
        actor_type="api_client",
        metadata={
            "cascade": cascade,
            "cascade_count": len(deleted_ids) - 1,
            "deleted_ids": [str(uid) for uid in deleted_ids],
        },
    )

    return SoftDeleteResponse(
        deleted_id=artifact_id,
        cascade_count=len(deleted_ids) - 1,
        deleted_ids=deleted_ids,
        deleted_at=deleted_at,
    )


# =============================================================================
# Physical Deletion (Phase 2, Item 7)
# =============================================================================


async def physical_delete_artifact(
    artifact_id: UUID,
    tenant_id: int,
    cascade: bool = True,
) -> PhysicalDeleteResponse | None:
    """Physically delete an artifact and all associated data.

    Deletion order respects FK constraints:
    1. Collect all artifact IDs (target + descendants if cascade)
    2. Delete embedding vectors from mimir_vectors.vec_{type} tables
    3. Delete embedding master rows
    4. Delete relation rows (source or target)
    5. Delete provenance event rows
    6. Delete artifact rows (leaf-first via reverse depth ordering)

    Returns None if the artifact does not exist.
    Raises ValueError with "has_children" if cascade=False and children exist.
    """
    async with get_connection() as conn:
        # Verify artifact exists
        check = await conn.execute(
            f"""
            SELECT id FROM {SCHEMA_NAME}.artifact
            WHERE id = %s AND tenant_id = %s
            """,
            (str(artifact_id), tenant_id),
        )
        if not await check.fetchone():
            return None

        # Collect all artifact IDs to delete (with depth for leaf-first ordering)
        if cascade:
            tree_result = await conn.execute(
                f"""
                WITH RECURSIVE descendants AS (
                    SELECT id, 0 as depth
                    FROM {SCHEMA_NAME}.artifact
                    WHERE id = %s AND tenant_id = %s

                    UNION ALL

                    SELECT a.id, d.depth + 1
                    FROM {SCHEMA_NAME}.artifact a
                    INNER JOIN descendants d ON a.parent_artifact_id = d.id
                    WHERE a.tenant_id = %s
                )
                SELECT id, depth FROM descendants
                ORDER BY depth DESC
                """,
                (str(artifact_id), tenant_id, tenant_id),
            )
        else:
            # Check for children first
            children_check = await conn.execute(
                f"""
                SELECT COUNT(*) FROM {SCHEMA_NAME}.artifact
                WHERE parent_artifact_id = %s AND tenant_id = %s
                """,
                (str(artifact_id), tenant_id),
            )
            child_count = (await children_check.fetchone())[0]
            if child_count > 0:
                raise ValueError("has_children")

            tree_result = await conn.execute(
                f"""
                SELECT id, 0 as depth FROM {SCHEMA_NAME}.artifact
                WHERE id = %s AND tenant_id = %s
                """,
                (str(artifact_id), tenant_id),
            )

        tree_rows = await tree_result.fetchall()
        if not tree_rows:
            return None

        # All artifact IDs to delete (ordered leaf-first)
        all_ids = [UUID(row[0]) if isinstance(row[0], str) else row[0] for row in tree_rows]
        id_strings = [str(uid) for uid in all_ids]

        counts = {"artifacts": 0, "embeddings": 0, "relations": 0, "provenance_events": 0}

        # 1. Find and delete embedding vectors from child tables
        emb_result = await conn.execute(
            f"""
            SELECT e.id, et.vector_table_name
            FROM {SCHEMA_NAME}.embedding e
            JOIN {SCHEMA_NAME}.embedding_type et ON et.code = e.embedding_type
            WHERE e.artifact_id = ANY(%s) AND e.tenant_id = %s
            """,
            (id_strings, tenant_id),
        )
        emb_rows = await emb_result.fetchall()

        # Group by vector table for batch deletes
        vectors_by_table: dict[str, list[str]] = {}
        for emb_row in emb_rows:
            emb_id = str(emb_row[0])
            table_name = emb_row[1]
            vectors_by_table.setdefault(table_name, []).append(emb_id)

        for table_name, emb_ids in vectors_by_table.items():
            vec_del = await conn.execute(
                f"DELETE FROM {VECTOR_SCHEMA}.{table_name} WHERE embedding_id = ANY(%s)",
                (emb_ids,),
            )
            counts["embeddings"] += vec_del.rowcount

        # 2. Delete embedding master rows
        emb_del = await conn.execute(
            f"DELETE FROM {SCHEMA_NAME}.embedding WHERE artifact_id = ANY(%s) AND tenant_id = %s",
            (id_strings, tenant_id),
        )
        # embeddings count already tracked via vectors; master rows match

        # 3. Delete relations (where any of our artifacts is source or target)
        rel_del = await conn.execute(
            f"""
            DELETE FROM {SCHEMA_NAME}.relation
            WHERE tenant_id = %s AND (source_id = ANY(%s) OR target_id = ANY(%s))
            """,
            (tenant_id, id_strings, id_strings),
        )
        counts["relations"] = rel_del.rowcount

        # 4. Delete provenance events
        prov_del = await conn.execute(
            f"""
            DELETE FROM {SCHEMA_NAME}.provenance_event
            WHERE tenant_id = %s AND entity_type = 'artifact' AND entity_id = ANY(%s)
            """,
            (tenant_id, id_strings),
        )
        counts["provenance_events"] = prov_del.rowcount

        # 5. Delete artifacts (leaf-first — they're already ordered by depth DESC)
        for id_str in id_strings:
            await conn.execute(
                f"DELETE FROM {SCHEMA_NAME}.artifact WHERE id = %s AND tenant_id = %s",
                (id_str, tenant_id),
            )
        counts["artifacts"] = len(id_strings)

        await conn.commit()

    # Log provenance event (on a best-effort basis — the artifact is gone,
    # so we log against the original ID with a special entity_type)
    await provenance_service.log_action(
        tenant_id=tenant_id,
        entity_type="artifact",
        entity_id=artifact_id,
        action="physical_delete",
        actor_type="api_client",
        metadata={
            "cascade": cascade,
            "deleted_counts": counts,
            "deleted_ids": [str(uid) for uid in all_ids],
        },
    )

    return PhysicalDeleteResponse(
        deleted_id=artifact_id,
        deleted=counts,
    )


# =============================================================================
# Row Mapping
# =============================================================================


def _row_to_artifact_response(row: tuple) -> ArtifactResponse:
    """Convert database row to ArtifactResponse.

    Row columns (16 total, with deleted_at):
    0: id, 1: tenant_id, 2: artifact_type, 3: parent_artifact_id,
    4: start_offset, 5: end_offset, 6: position_metadata,
    7: title, 8: content, 9: content_hash,
    10: source, 11: source_system, 12: external_id, 13: metadata,
    14: created_at, 15: deleted_at
    """
    return ArtifactResponse(
        id=UUID(row[0]) if isinstance(row[0], str) else row[0],
        tenant_id=row[1],
        artifact_type=row[2],
        parent_artifact_id=UUID(row[3]) if isinstance(row[3], str) else row[3] if row[3] else None,
        start_offset=row[4],
        end_offset=row[5],
        position_metadata=row[6],
        title=row[7],
        content=row[8],
        content_hash=row[9],
        source=row[10],
        source_system=row[11],
        external_id=row[12],
        metadata=row[13],
        created_at=row[14],
        deleted_at=row[15] if len(row) > 15 else None,
    )