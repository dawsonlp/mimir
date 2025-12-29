"""Artifact service - database operations for artifacts and versions (V2)."""

import hashlib

from psycopg.types.json import Json

from mimir.database import get_connection
from mimir.schemas.artifact import (
    ArtifactCreate,
    ArtifactListResponse,
    ArtifactResponse,
    ArtifactUpdate,
    ArtifactVersionResponse,
)

SCHEMA_NAME = "mimirdata"


def _hash_content(content: str | None) -> str | None:
    """Generate SHA-256 hash of content."""
    if content is None:
        return None
    return hashlib.sha256(content.encode()).hexdigest()


async def create_artifact(tenant_id: int, data: ArtifactCreate) -> ArtifactResponse:
    """Create a new artifact."""
    content_hash = _hash_content(data.content)

    async with get_connection() as conn:
        result = await conn.execute(
            f"""
            INSERT INTO {SCHEMA_NAME}.artifact
                (tenant_id, artifact_type, parent_artifact_id,
                 start_offset, end_offset, position_metadata,
                 title, content, content_hash,
                 source, source_system, external_id, metadata)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id, tenant_id, artifact_type, parent_artifact_id,
                      start_offset, end_offset, position_metadata,
                      title, content, content_hash,
                      source, source_system, external_id, metadata,
                      created_at, updated_at
            """,
            (
                tenant_id,
                data.artifact_type,
                data.parent_artifact_id,
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

    return _row_to_artifact_response(row)


async def get_artifact(artifact_id: int, tenant_id: int) -> ArtifactResponse | None:
    """Get artifact by ID."""
    async with get_connection() as conn:
        result = await conn.execute(
            f"""
            SELECT id, tenant_id, artifact_type, parent_artifact_id,
                   start_offset, end_offset, position_metadata,
                   title, content, content_hash,
                   source, source_system, external_id, metadata,
                   created_at, updated_at
            FROM {SCHEMA_NAME}.artifact
            WHERE id = %s AND tenant_id = %s
            """,
            (artifact_id, tenant_id),
        )
        row = await result.fetchone()

    if not row:
        return None

    return _row_to_artifact_response(row)


async def list_artifacts(
    tenant_id: int,
    page: int = 1,
    page_size: int = 50,
    artifact_type: str | None = None,
    parent_artifact_id: int | None = None,
) -> ArtifactListResponse:
    """List artifacts for a tenant with pagination."""
    offset = (page - 1) * page_size

    async with get_connection() as conn:
        where_clause = "WHERE tenant_id = %s"
        params: list = [tenant_id]

        if artifact_type:
            where_clause += " AND artifact_type = %s"
            params.append(artifact_type)
        if parent_artifact_id is not None:
            where_clause += " AND parent_artifact_id = %s"
            params.append(parent_artifact_id)

        # Get total count
        count_result = await conn.execute(
            f"SELECT COUNT(*) FROM {SCHEMA_NAME}.artifact {where_clause}",
            params,
        )
        total = (await count_result.fetchone())[0]

        # Get page
        result = await conn.execute(
            f"""
            SELECT id, tenant_id, artifact_type, parent_artifact_id,
                   start_offset, end_offset, position_metadata,
                   title, content, content_hash,
                   source, source_system, external_id, metadata,
                   created_at, updated_at
            FROM {SCHEMA_NAME}.artifact
            {where_clause}
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
            """,
            params + [page_size, offset],
        )
        rows = await result.fetchall()

    items = [_row_to_artifact_response(row) for row in rows]

    return ArtifactListResponse(
        items=items, total=total, page=page, page_size=page_size
    )


async def update_artifact(
    artifact_id: int, tenant_id: int, data: ArtifactUpdate
) -> ArtifactResponse | None:
    """Update artifact."""
    updates = []
    params = []

    if data.artifact_type is not None:
        updates.append("artifact_type = %s")
        params.append(data.artifact_type)
    if data.parent_artifact_id is not None:
        updates.append("parent_artifact_id = %s")
        params.append(data.parent_artifact_id)
    if data.start_offset is not None:
        updates.append("start_offset = %s")
        params.append(data.start_offset)
    if data.end_offset is not None:
        updates.append("end_offset = %s")
        params.append(data.end_offset)
    if data.position_metadata is not None:
        updates.append("position_metadata = %s")
        params.append(Json(data.position_metadata))
    if data.title is not None:
        updates.append("title = %s")
        params.append(data.title)
    if data.content is not None:
        updates.append("content = %s")
        params.append(data.content)
        updates.append("content_hash = %s")
        params.append(_hash_content(data.content))
    if data.source is not None:
        updates.append("source = %s")
        params.append(data.source)
    if data.source_system is not None:
        updates.append("source_system = %s")
        params.append(data.source_system)
    if data.external_id is not None:
        updates.append("external_id = %s")
        params.append(data.external_id)
    if data.metadata is not None:
        updates.append("metadata = %s")
        params.append(Json(data.metadata))

    if not updates:
        return await get_artifact(artifact_id, tenant_id)

    params.extend([artifact_id, tenant_id])

    async with get_connection() as conn:
        result = await conn.execute(
            f"""
            UPDATE {SCHEMA_NAME}.artifact
            SET {", ".join(updates)}, updated_at = NOW()
            WHERE id = %s AND tenant_id = %s
            RETURNING id, tenant_id, artifact_type, parent_artifact_id,
                      start_offset, end_offset, position_metadata,
                      title, content, content_hash,
                      source, source_system, external_id, metadata,
                      created_at, updated_at
            """,
            params,
        )
        row = await result.fetchone()
        await conn.commit()

    if not row:
        return None

    return _row_to_artifact_response(row)


async def delete_artifact(artifact_id: int, tenant_id: int) -> bool:
    """Delete an artifact."""
    async with get_connection() as conn:
        result = await conn.execute(
            f"""
            DELETE FROM {SCHEMA_NAME}.artifact
            WHERE id = %s AND tenant_id = %s
            RETURNING id
            """,
            (artifact_id, tenant_id),
        )
        row = await result.fetchone()
        await conn.commit()

    return row is not None


async def get_children(artifact_id: int, tenant_id: int) -> list[ArtifactResponse]:
    """Get all child artifacts."""
    async with get_connection() as conn:
        result = await conn.execute(
            f"""
            SELECT id, tenant_id, artifact_type, parent_artifact_id,
                   start_offset, end_offset, position_metadata,
                   title, content, content_hash,
                   source, source_system, external_id, metadata,
                   created_at, updated_at
            FROM {SCHEMA_NAME}.artifact
            WHERE parent_artifact_id = %s AND tenant_id = %s
            ORDER BY start_offset NULLS LAST, created_at
            """,
            (artifact_id, tenant_id),
        )
        rows = await result.fetchall()

    return [_row_to_artifact_response(row) for row in rows]


# Version operations (artifact_version table)

async def create_version(
    artifact_id: int,
    tenant_id: int,
    title: str | None = None,
    content: str | None = None,
    change_reason: str | None = None,
    changed_by: str | None = None,
    metadata: dict | None = None,
) -> ArtifactVersionResponse | None:
    """Create a new version of an artifact."""
    content_hash = _hash_content(content)

    async with get_connection() as conn:
        # Verify artifact exists
        check = await conn.execute(
            f"SELECT id FROM {SCHEMA_NAME}.artifact WHERE id = %s AND tenant_id = %s",
            (artifact_id, tenant_id),
        )
        if not await check.fetchone():
            return None

        # Get next version number
        version_result = await conn.execute(
            f"""
            SELECT COALESCE(MAX(version_number), 0) + 1
            FROM {SCHEMA_NAME}.artifact_version
            WHERE artifact_id = %s
            """,
            (artifact_id,),
        )
        next_version = (await version_result.fetchone())[0]

        # Insert version
        result = await conn.execute(
            f"""
            INSERT INTO {SCHEMA_NAME}.artifact_version
                (artifact_id, version_number, title, content, content_hash,
                 change_reason, changed_by, metadata)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id, artifact_id, version_number, title, content, content_hash,
                      change_reason, changed_by, metadata, created_at
            """,
            (
                artifact_id,
                next_version,
                title,
                content,
                content_hash,
                change_reason,
                changed_by,
                Json(metadata) if metadata else None,
            ),
        )
        row = await result.fetchone()
        await conn.commit()

    return _row_to_version_response(row)


async def get_versions(
    artifact_id: int, tenant_id: int
) -> list[ArtifactVersionResponse]:
    """Get all versions of an artifact."""
    async with get_connection() as conn:
        # Verify artifact
        check = await conn.execute(
            f"SELECT id FROM {SCHEMA_NAME}.artifact WHERE id = %s AND tenant_id = %s",
            (artifact_id, tenant_id),
        )
        if not await check.fetchone():
            return []

        result = await conn.execute(
            f"""
            SELECT id, artifact_id, version_number, title, content, content_hash,
                   change_reason, changed_by, metadata, created_at
            FROM {SCHEMA_NAME}.artifact_version
            WHERE artifact_id = %s
            ORDER BY version_number DESC
            """,
            (artifact_id,),
        )
        rows = await result.fetchall()

    return [_row_to_version_response(row) for row in rows]


async def get_version(
    artifact_id: int, version_number: int, tenant_id: int
) -> ArtifactVersionResponse | None:
    """Get a specific version of an artifact."""
    async with get_connection() as conn:
        # Verify artifact
        check = await conn.execute(
            f"SELECT id FROM {SCHEMA_NAME}.artifact WHERE id = %s AND tenant_id = %s",
            (artifact_id, tenant_id),
        )
        if not await check.fetchone():
            return None

        result = await conn.execute(
            f"""
            SELECT id, artifact_id, version_number, title, content, content_hash,
                   change_reason, changed_by, metadata, created_at
            FROM {SCHEMA_NAME}.artifact_version
            WHERE artifact_id = %s AND version_number = %s
            """,
            (artifact_id, version_number),
        )
        row = await result.fetchone()

    if not row:
        return None

    return _row_to_version_response(row)


def _row_to_artifact_response(row: tuple) -> ArtifactResponse:
    """Convert database row to ArtifactResponse."""
    return ArtifactResponse(
        id=row[0],
        tenant_id=row[1],
        artifact_type=row[2],
        parent_artifact_id=row[3],
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
        updated_at=row[15],
    )


def _row_to_version_response(row: tuple) -> ArtifactVersionResponse:
    """Convert database row to ArtifactVersionResponse."""
    return ArtifactVersionResponse(
        id=row[0],
        artifact_id=row[1],
        version_number=row[2],
        title=row[3],
        content=row[4],
        content_hash=row[5],
        change_reason=row[6],
        changed_by=row[7],
        metadata=row[8],
        created_at=row[9],
    )
