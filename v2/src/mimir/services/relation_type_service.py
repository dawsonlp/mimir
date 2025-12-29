"""Relation type vocabulary service (V2 - NEW)."""

from mimir.database import get_connection
from mimir.schemas.relation_type import (
    RelationTypeCreate,
    RelationTypeResponse,
    RelationTypeUpdate,
)

SCHEMA_NAME = "mimirdata"


async def get_relation_type(code: str) -> RelationTypeResponse | None:
    """Get relation type by code."""
    async with get_connection() as conn:
        result = await conn.execute(
            f"""
            SELECT code, display_name, description, inverse_code,
                   is_symmetric, is_active, sort_order, created_at
            FROM {SCHEMA_NAME}.relation_type
            WHERE code = %s
            """,
            (code,),
        )
        row = await result.fetchone()

    if not row:
        return None

    return RelationTypeResponse(
        code=row[0],
        display_name=row[1],
        description=row[2],
        inverse_code=row[3],
        is_symmetric=row[4],
        is_active=row[5],
        sort_order=row[6],
        created_at=row[7],
    )


async def list_relation_types(active_only: bool = True) -> list[RelationTypeResponse]:
    """List all relation types."""
    async with get_connection() as conn:
        query = f"""
            SELECT code, display_name, description, inverse_code,
                   is_symmetric, is_active, sort_order, created_at
            FROM {SCHEMA_NAME}.relation_type
        """
        if active_only:
            query += " WHERE is_active = true"
        query += " ORDER BY sort_order, code"

        result = await conn.execute(query)
        rows = await result.fetchall()

    return [
        RelationTypeResponse(
            code=row[0],
            display_name=row[1],
            description=row[2],
            inverse_code=row[3],
            is_symmetric=row[4],
            is_active=row[5],
            sort_order=row[6],
            created_at=row[7],
        )
        for row in rows
    ]


async def create_relation_type(data: RelationTypeCreate) -> RelationTypeResponse:
    """Create a new relation type."""
    async with get_connection() as conn:
        result = await conn.execute(
            f"""
            INSERT INTO {SCHEMA_NAME}.relation_type
                (code, display_name, description, inverse_code,
                 is_symmetric, is_active, sort_order)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING code, display_name, description, inverse_code,
                      is_symmetric, is_active, sort_order, created_at
            """,
            (
                data.code,
                data.display_name,
                data.description,
                data.inverse_code,
                data.is_symmetric,
                data.is_active,
                data.sort_order,
            ),
        )
        row = await result.fetchone()
        await conn.commit()

    return RelationTypeResponse(
        code=row[0],
        display_name=row[1],
        description=row[2],
        inverse_code=row[3],
        is_symmetric=row[4],
        is_active=row[5],
        sort_order=row[6],
        created_at=row[7],
    )


async def update_relation_type(
    code: str, data: RelationTypeUpdate
) -> RelationTypeResponse | None:
    """Update a relation type."""
    updates = []
    params = []

    if data.display_name is not None:
        updates.append("display_name = %s")
        params.append(data.display_name)
    if data.description is not None:
        updates.append("description = %s")
        params.append(data.description)
    if data.inverse_code is not None:
        updates.append("inverse_code = %s")
        params.append(data.inverse_code)
    if data.is_symmetric is not None:
        updates.append("is_symmetric = %s")
        params.append(data.is_symmetric)
    if data.is_active is not None:
        updates.append("is_active = %s")
        params.append(data.is_active)
    if data.sort_order is not None:
        updates.append("sort_order = %s")
        params.append(data.sort_order)

    if not updates:
        return await get_relation_type(code)

    params.append(code)

    async with get_connection() as conn:
        result = await conn.execute(
            f"""
            UPDATE {SCHEMA_NAME}.relation_type
            SET {", ".join(updates)}
            WHERE code = %s
            RETURNING code, display_name, description, inverse_code,
                      is_symmetric, is_active, sort_order, created_at
            """,
            params,
        )
        row = await result.fetchone()
        await conn.commit()

    if not row:
        return None

    return RelationTypeResponse(
        code=row[0],
        display_name=row[1],
        description=row[2],
        inverse_code=row[3],
        is_symmetric=row[4],
        is_active=row[5],
        sort_order=row[6],
        created_at=row[7],
    )


async def validate_relation_type(code: str) -> bool:
    """Check if relation type exists and is active."""
    async with get_connection() as conn:
        result = await conn.execute(
            f"""
            SELECT 1 FROM {SCHEMA_NAME}.relation_type
            WHERE code = %s AND is_active = true
            """,
            (code,),
        )
        row = await result.fetchone()
    return row is not None


async def get_inverse_type(code: str) -> RelationTypeResponse | None:
    """Get the inverse relation type if defined."""
    relation = await get_relation_type(code)
    if not relation or not relation.inverse_code:
        return None
    return await get_relation_type(relation.inverse_code)
