"""Artifact type vocabulary service (V2 - NEW)."""

from mimir.database import get_connection
from mimir.schemas.artifact_type import (
    ArtifactTypeCreate,
    ArtifactTypeResponse,
    ArtifactTypeUpdate,
)

SCHEMA_NAME = "mimirdata"


async def get_artifact_type(code: str) -> ArtifactTypeResponse | None:
    """Get artifact type by code."""
    async with get_connection() as conn:
        result = await conn.execute(
            f"""
            SELECT code, display_name, description, category,
                   is_active, sort_order, created_at
            FROM {SCHEMA_NAME}.artifact_type
            WHERE code = %s
            """,
            (code,),
        )
        row = await result.fetchone()

    if not row:
        return None

    return ArtifactTypeResponse(
        code=row[0],
        display_name=row[1],
        description=row[2],
        category=row[3],
        is_active=row[4],
        sort_order=row[5],
        created_at=row[6],
    )


async def list_artifact_types(
    active_only: bool = True,
    category: str | None = None,
) -> list[ArtifactTypeResponse]:
    """List all artifact types."""
    async with get_connection() as conn:
        query = f"""
            SELECT code, display_name, description, category,
                   is_active, sort_order, created_at
            FROM {SCHEMA_NAME}.artifact_type
            WHERE 1=1
        """
        params = []
        
        if active_only:
            query += " AND is_active = true"
        if category:
            query += " AND category = %s"
            params.append(category)
        
        query += " ORDER BY sort_order, code"
        
        result = await conn.execute(query, params)
        rows = await result.fetchall()

    return [
        ArtifactTypeResponse(
            code=row[0],
            display_name=row[1],
            description=row[2],
            category=row[3],
            is_active=row[4],
            sort_order=row[5],
            created_at=row[6],
        )
        for row in rows
    ]


async def create_artifact_type(data: ArtifactTypeCreate) -> ArtifactTypeResponse:
    """Create a new artifact type."""
    async with get_connection() as conn:
        result = await conn.execute(
            f"""
            INSERT INTO {SCHEMA_NAME}.artifact_type
                (code, display_name, description, category, is_active, sort_order)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING code, display_name, description, category,
                      is_active, sort_order, created_at
            """,
            (
                data.code,
                data.display_name,
                data.description,
                data.category,
                data.is_active,
                data.sort_order,
            ),
        )
        row = await result.fetchone()
        await conn.commit()

    return ArtifactTypeResponse(
        code=row[0],
        display_name=row[1],
        description=row[2],
        category=row[3],
        is_active=row[4],
        sort_order=row[5],
        created_at=row[6],
    )


async def update_artifact_type(
    code: str, data: ArtifactTypeUpdate
) -> ArtifactTypeResponse | None:
    """Update an artifact type."""
    updates = []
    params = []

    if data.display_name is not None:
        updates.append("display_name = %s")
        params.append(data.display_name)
    if data.description is not None:
        updates.append("description = %s")
        params.append(data.description)
    if data.category is not None:
        updates.append("category = %s")
        params.append(data.category)
    if data.is_active is not None:
        updates.append("is_active = %s")
        params.append(data.is_active)
    if data.sort_order is not None:
        updates.append("sort_order = %s")
        params.append(data.sort_order)

    if not updates:
        return await get_artifact_type(code)

    params.append(code)

    async with get_connection() as conn:
        result = await conn.execute(
            f"""
            UPDATE {SCHEMA_NAME}.artifact_type
            SET {", ".join(updates)}
            WHERE code = %s
            RETURNING code, display_name, description, category,
                      is_active, sort_order, created_at
            """,
            params,
        )
        row = await result.fetchone()
        await conn.commit()

    if not row:
        return None

    return ArtifactTypeResponse(
        code=row[0],
        display_name=row[1],
        description=row[2],
        category=row[3],
        is_active=row[4],
        sort_order=row[5],
        created_at=row[6],
    )


async def validate_artifact_type(code: str) -> bool:
    """Check if artifact type exists and is active."""
    async with get_connection() as conn:
        result = await conn.execute(
            f"""
            SELECT 1 FROM {SCHEMA_NAME}.artifact_type
            WHERE code = %s AND is_active = true
            """,
            (code,),
        )
        row = await result.fetchone()
    return row is not None
