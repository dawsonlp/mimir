"""Artifact service - database operations for artifacts and versions."""

import hashlib

from psycopg.types.json import Json

from mimir.database import get_connection
from mimir.models import SCHEMA_NAME
from mimir.schemas.artifact import (
    ArtifactCreate,
    ArtifactDetailResponse,
    ArtifactListResponse,
    ArtifactResponse,
    ArtifactUpdate,
    ArtifactVersionCreate,
    ArtifactVersionResponse,
)


def _hash_content(content: str) -> str:
    """Generate SHA-256 hash of content."""
    return hashlib.sha256(content.encode()).hexdigest()


async def create_artifact(
    tenant_id: int, data: ArtifactCreate
) -> ArtifactDetailResponse:
    """Create a new artifact with initial version."""
    content_hash = _hash_content(data.content)

    async with get_connection() as conn:
        # Insert artifact
        result = await conn.execute(
            f"""
            INSERT INTO {SCHEMA_NAME}.artifacts
                (tenant_id, artifact_type, source, source_system, external_id, title, metadata)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id, tenant_id, artifact_type, source, source_system, external_id, title,
                      metadata, created_at, updated_at
            """,
            (
                tenant_id,
                data.artifact_type.value,
                data.source,
                data.source_system,
                data.external_id,
                data.title,
                Json(data.metadata),
            ),
        )
        artifact_row = await result.fetchone()

        # Insert initial version
        version_result = await conn.execute(
            f"""
            INSERT INTO {SCHEMA_NAME}.artifact_versions
                (artifact_id, version_number, content, content_hash, created_by)
            VALUES (%s, 1, %s, %s, 'system')
            RETURNING id, artifact_id, version_number, content, content_hash,
                      created_at, created_by
            """,
            (artifact_row[0], data.content, content_hash),
        )
        version_row = await version_result.fetchone()
        await conn.commit()

    artifact = ArtifactResponse(
        id=artifact_row[0],
        tenant_id=artifact_row[1],
        artifact_type=artifact_row[2],
        source=artifact_row[3],
        source_system=artifact_row[4],
        external_id=artifact_row[5],
        title=artifact_row[6],
        metadata=artifact_row[7],
        created_at=artifact_row[8],
        updated_at=artifact_row[9],
    )
    version = ArtifactVersionResponse(
        id=version_row[0],
        artifact_id=version_row[1],
        version_number=version_row[2],
        content=version_row[3],
        content_hash=version_row[4],
        created_at=version_row[5],
        created_by=version_row[6],
    )

    return ArtifactDetailResponse(**artifact.model_dump(), latest_version=version)


async def get_artifact(artifact_id: int, tenant_id: int) -> ArtifactDetailResponse | None:
    """Get artifact by ID with latest version."""
    async with get_connection() as conn:
        result = await conn.execute(
            f"""
            SELECT a.id, a.tenant_id, a.artifact_type, a.source, a.source_system, a.external_id,
                   a.title, a.metadata, a.created_at, a.updated_at,
                   v.id, v.artifact_id, v.version_number, v.content, v.content_hash,
                   v.created_at, v.created_by
            FROM {SCHEMA_NAME}.artifacts a
            LEFT JOIN {SCHEMA_NAME}.artifact_versions v ON v.artifact_id = a.id
                AND v.version_number = (
                    SELECT MAX(version_number) FROM {SCHEMA_NAME}.artifact_versions
                    WHERE artifact_id = a.id
                )
            WHERE a.id = %s AND a.tenant_id = %s
            """,
            (artifact_id, tenant_id),
        )
        row = await result.fetchone()

    if not row:
        return None

    artifact = ArtifactResponse(
        id=row[0],
        tenant_id=row[1],
        artifact_type=row[2],
        source=row[3],
        source_system=row[4],
        external_id=row[5],
        title=row[6],
        metadata=row[7],
        created_at=row[8],
        updated_at=row[9],
    )

    latest_version = None
    if row[10]:  # version exists
        latest_version = ArtifactVersionResponse(
            id=row[10],
            artifact_id=row[11],
            version_number=row[12],
            content=row[13],
            content_hash=row[14],
            created_at=row[15],
            created_by=row[16],
        )

    return ArtifactDetailResponse(**artifact.model_dump(), latest_version=latest_version)


async def list_artifacts(
    tenant_id: int,
    page: int = 1,
    page_size: int = 20,
    artifact_type: str | None = None,
) -> ArtifactListResponse:
    """List artifacts for a tenant with pagination."""
    offset = (page - 1) * page_size

    async with get_connection() as conn:
        # Build query with optional filter
        where_clause = "WHERE a.tenant_id = %s"
        params: list = [tenant_id]

        if artifact_type:
            where_clause += " AND a.artifact_type = %s"
            params.append(artifact_type)

        # Get total count
        count_result = await conn.execute(
            f"SELECT COUNT(*) FROM {SCHEMA_NAME}.artifacts a {where_clause}",
            params,
        )
        total = (await count_result.fetchone())[0]

        # Get page of artifacts
        result = await conn.execute(
            f"""
            SELECT id, tenant_id, artifact_type, source, source_system, external_id,
                   title, metadata, created_at, updated_at
            FROM {SCHEMA_NAME}.artifacts a
            {where_clause}
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
            """,
            params + [page_size, offset],
        )
        rows = await result.fetchall()

    items = [
        ArtifactResponse(
            id=row[0],
            tenant_id=row[1],
            artifact_type=row[2],
            source=row[3],
            source_system=row[4],
            external_id=row[5],
            title=row[6],
            metadata=row[7],
            created_at=row[8],
            updated_at=row[9],
        )
        for row in rows
    ]

    return ArtifactListResponse(
        items=items, total=total, page=page, page_size=page_size
    )


async def update_artifact(
    artifact_id: int, tenant_id: int, data: ArtifactUpdate
) -> ArtifactResponse | None:
    """Update artifact metadata."""
    # Build dynamic UPDATE
    updates = []
    params = []

    if data.title is not None:
        updates.append("title = %s")
        params.append(data.title)
    if data.metadata is not None:
        updates.append("metadata = %s")
        params.append(Json(data.metadata))

    if not updates:
        # Nothing to update, just fetch current
        return await _get_artifact_basic(artifact_id, tenant_id)

    params.extend([artifact_id, tenant_id])

    async with get_connection() as conn:
        result = await conn.execute(
            f"""
            UPDATE {SCHEMA_NAME}.artifacts
            SET {", ".join(updates)}
            WHERE id = %s AND tenant_id = %s
            RETURNING id, tenant_id, artifact_type, source, source_system, external_id,
                      title, metadata, created_at, updated_at
            """,
            params,
        )
        row = await result.fetchone()
        await conn.commit()

    if not row:
        return None

    return ArtifactResponse(
        id=row[0],
        tenant_id=row[1],
        artifact_type=row[2],
        source=row[3],
        source_system=row[4],
        external_id=row[5],
        title=row[6],
        metadata=row[7],
        created_at=row[8],
        updated_at=row[9],
    )


async def _get_artifact_basic(artifact_id: int, tenant_id: int) -> ArtifactResponse | None:
    """Get artifact without version info."""
    async with get_connection() as conn:
        result = await conn.execute(
            f"""
            SELECT id, tenant_id, artifact_type, source, source_system, external_id,
                   title, metadata, created_at, updated_at
            FROM {SCHEMA_NAME}.artifacts
            WHERE id = %s AND tenant_id = %s
            """,
            (artifact_id, tenant_id),
        )
        row = await result.fetchone()

    if not row:
        return None

    return ArtifactResponse(
        id=row[0],
        tenant_id=row[1],
        artifact_type=row[2],
        source=row[3],
        source_system=row[4],
        external_id=row[5],
        title=row[6],
        metadata=row[7],
        created_at=row[8],
        updated_at=row[9],
    )


async def add_version(
    artifact_id: int, tenant_id: int, data: ArtifactVersionCreate
) -> ArtifactVersionResponse | None:
    """Add a new version to an artifact."""
    content_hash = _hash_content(data.content)

    async with get_connection() as conn:
        # Verify artifact exists and belongs to tenant
        check = await conn.execute(
            f"SELECT id FROM {SCHEMA_NAME}.artifacts WHERE id = %s AND tenant_id = %s",
            (artifact_id, tenant_id),
        )
        if not await check.fetchone():
            return None

        # Get next version number
        version_result = await conn.execute(
            f"""
            SELECT COALESCE(MAX(version_number), 0) + 1
            FROM {SCHEMA_NAME}.artifact_versions
            WHERE artifact_id = %s
            """,
            (artifact_id,),
        )
        next_version = (await version_result.fetchone())[0]

        # Insert new version
        result = await conn.execute(
            f"""
            INSERT INTO {SCHEMA_NAME}.artifact_versions
                (artifact_id, version_number, content, content_hash, created_by)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id, artifact_id, version_number, content, content_hash,
                      created_at, created_by
            """,
            (artifact_id, next_version, data.content, content_hash, data.created_by),
        )
        row = await result.fetchone()
        await conn.commit()

    return ArtifactVersionResponse(
        id=row[0],
        artifact_id=row[1],
        version_number=row[2],
        content=row[3],
        content_hash=row[4],
        created_at=row[5],
        created_by=row[6],
    )


async def get_versions(
    artifact_id: int, tenant_id: int
) -> list[ArtifactVersionResponse]:
    """Get all versions of an artifact."""
    async with get_connection() as conn:
        # Verify artifact belongs to tenant
        check = await conn.execute(
            f"SELECT id FROM {SCHEMA_NAME}.artifacts WHERE id = %s AND tenant_id = %s",
            (artifact_id, tenant_id),
        )
        if not await check.fetchone():
            return []

        result = await conn.execute(
            f"""
            SELECT id, artifact_id, version_number, content, content_hash,
                   created_at, created_by
            FROM {SCHEMA_NAME}.artifact_versions
            WHERE artifact_id = %s
            ORDER BY version_number DESC
            """,
            (artifact_id,),
        )
        rows = await result.fetchall()

    return [
        ArtifactVersionResponse(
            id=row[0],
            artifact_id=row[1],
            version_number=row[2],
            content=row[3],
            content_hash=row[4],
            created_at=row[5],
            created_by=row[6],
        )
        for row in rows
    ]


async def delete_artifact(artifact_id: int, tenant_id: int) -> bool:
    """Delete an artifact and all its versions."""
    async with get_connection() as conn:
        result = await conn.execute(
            f"""
            DELETE FROM {SCHEMA_NAME}.artifacts
            WHERE id = %s AND tenant_id = %s
            RETURNING id
            """,
            (artifact_id, tenant_id),
        )
        row = await result.fetchone()
        await conn.commit()

    return row is not None
