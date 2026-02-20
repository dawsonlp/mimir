"""Artifact service - database operations for artifacts.

Append-only data model — artifacts are never updated or deleted.
Tenant-level deletion via FK CASCADE is the only cleanup mechanism.

V2 Changes:
- UUID primary keys (client-generated or server-generated)
- Append-only: no update or delete operations
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
)
from mimir.services import provenance_service

SCHEMA_NAME = "mimirdata"
VECTOR_SCHEMA = "mimir_vectors"

# Standard SELECT columns for artifact (15 columns, append-only — no deleted_at)
_ARTIFACT_COLUMNS = """
    id, tenant_id, artifact_type, parent_artifact_id,
    start_offset, end_offset, position_metadata,
    title, content, content_hash,
    source, source_system, external_id, metadata,
    created_at
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
) -> ArtifactResponse | None:
    """Get artifact by UUID."""
    async with get_connection() as conn:
        result = await conn.execute(
            f"""
            SELECT {_ARTIFACT_COLUMNS}
            FROM {SCHEMA_NAME}.artifact
            WHERE id = %s AND tenant_id = %s
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
    """Get artifact by external ID."""
    async with get_connection() as conn:
        result = await conn.execute(
            f"""
            SELECT {_ARTIFACT_COLUMNS}
            FROM {SCHEMA_NAME}.artifact
            WHERE tenant_id = %s AND source_system = %s AND external_id = %s
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
) -> ArtifactListResponse:
    """List artifacts for a tenant with pagination or batch retrieval.

    When `ids` is provided, retrieves specific artifacts by UUID (batch mode).
    Batch mode ignores pagination parameters and returns artifacts in the
    order of requested IDs.
    """
    # Batch retrieval mode
    if ids is not None:
        return await _get_artifacts_by_ids(tenant_id, ids)

    # Standard pagination mode
    async with get_connection() as conn:
        where_clause = "WHERE tenant_id = %s"
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
    tenant_id: int, ids: list[UUID]
) -> ArtifactListResponse:
    """Retrieve artifacts by UUIDs, preserving request order.

    Uses PostgreSQL ANY() for efficient batch lookup.
    Missing IDs are silently omitted from results.
    """
    if not ids:
        return ArtifactListResponse(items=[], total=0, limit=0, offset=0)

    # Convert UUIDs to strings for query
    id_strings = [str(id) for id in ids]

    async with get_connection() as conn:
        result = await conn.execute(
            f"""
            SELECT {_ARTIFACT_COLUMNS}
            FROM {SCHEMA_NAME}.artifact
            WHERE tenant_id = %s AND id = ANY(%s)
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
    artifact_id: UUID, tenant_id: int
) -> list[ArtifactResponse]:
    """Get all child artifacts (for positional types like chunks, quotes)."""
    async with get_connection() as conn:
        result = await conn.execute(
            f"""
            SELECT {_ARTIFACT_COLUMNS}
            FROM {SCHEMA_NAME}.artifact
            WHERE parent_artifact_id = %s AND tenant_id = %s
            ORDER BY start_offset NULLS LAST, created_at
            """,
            (str(artifact_id), tenant_id),
        )
        rows = await result.fetchall()

    return [_row_to_artifact_response(row) for row in rows]


# =============================================================================
# Row Mapping
# =============================================================================


def _row_to_artifact_response(row: tuple) -> ArtifactResponse:
    """Convert database row to ArtifactResponse.

    Row columns (15 total, append-only):
    0: id, 1: tenant_id, 2: artifact_type, 3: parent_artifact_id,
    4: start_offset, 5: end_offset, 6: position_metadata,
    7: title, 8: content, 9: content_hash,
    10: source, 11: source_system, 12: external_id, 13: metadata,
    14: created_at
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
    )