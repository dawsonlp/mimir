"""Tenant service - database operations for tenants (V2)."""

from mimir.database import get_connection
from mimir.schemas.tenant import TenantCreate, TenantResponse, TenantUpdate

# Schema name for all tables
SCHEMA_NAME = "mimirdata"


async def create_tenant(data: TenantCreate) -> TenantResponse:
    """Create a new tenant."""
    async with get_connection() as conn:
        result = await conn.execute(
            f"""
            INSERT INTO {SCHEMA_NAME}.tenant
                (shortname, name, tenant_type, description, is_active, metadata)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id, shortname, name, tenant_type, description,
                      is_active, created_at, metadata
            """,
            (
                data.shortname,
                data.name,
                data.tenant_type,  # TEXT now, not enum
                data.description,
                data.is_active,
                data.metadata,
            ),
        )
        row = await result.fetchone()
        await conn.commit()

    return TenantResponse(
        id=row[0],
        shortname=row[1],
        name=row[2],
        tenant_type=row[3],
        description=row[4],
        is_active=row[5],
        created_at=row[6],
        metadata=row[7],
    )


async def get_tenant(tenant_id: int) -> TenantResponse | None:
    """Get tenant by ID."""
    async with get_connection() as conn:
        result = await conn.execute(
            f"""
            SELECT id, shortname, name, tenant_type, description,
                   is_active, created_at, metadata
            FROM {SCHEMA_NAME}.tenant
            WHERE id = %s
            """,
            (tenant_id,),
        )
        row = await result.fetchone()

    if not row:
        return None

    return TenantResponse(
        id=row[0],
        shortname=row[1],
        name=row[2],
        tenant_type=row[3],
        description=row[4],
        is_active=row[5],
        created_at=row[6],
        metadata=row[7],
    )


async def get_tenant_by_shortname(shortname: str) -> TenantResponse | None:
    """Get tenant by shortname."""
    async with get_connection() as conn:
        result = await conn.execute(
            f"""
            SELECT id, shortname, name, tenant_type, description,
                   is_active, created_at, metadata
            FROM {SCHEMA_NAME}.tenant
            WHERE shortname = %s
            """,
            (shortname,),
        )
        row = await result.fetchone()

    if not row:
        return None

    return TenantResponse(
        id=row[0],
        shortname=row[1],
        name=row[2],
        tenant_type=row[3],
        description=row[4],
        is_active=row[5],
        created_at=row[6],
        metadata=row[7],
    )


async def list_tenants(active_only: bool = True) -> list[TenantResponse]:
    """List all tenants."""
    async with get_connection() as conn:
        query = f"""
            SELECT id, shortname, name, tenant_type, description,
                   is_active, created_at, metadata
            FROM {SCHEMA_NAME}.tenant
        """
        if active_only:
            query += " WHERE is_active = true"
        query += " ORDER BY shortname"

        result = await conn.execute(query)
        rows = await result.fetchall()

    return [
        TenantResponse(
            id=row[0],
            shortname=row[1],
            name=row[2],
            tenant_type=row[3],
            description=row[4],
            is_active=row[5],
            created_at=row[6],
            metadata=row[7],
        )
        for row in rows
    ]


async def update_tenant(tenant_id: int, data: TenantUpdate) -> TenantResponse | None:
    """Update a tenant."""
    updates = []
    params = []

    if data.name is not None:
        updates.append("name = %s")
        params.append(data.name)
    if data.tenant_type is not None:
        updates.append("tenant_type = %s")
        params.append(data.tenant_type)
    if data.description is not None:
        updates.append("description = %s")
        params.append(data.description)
    if data.is_active is not None:
        updates.append("is_active = %s")
        params.append(data.is_active)
    if data.metadata is not None:
        updates.append("metadata = %s")
        params.append(data.metadata)

    if not updates:
        return await get_tenant(tenant_id)

    params.append(tenant_id)

    async with get_connection() as conn:
        result = await conn.execute(
            f"""
            UPDATE {SCHEMA_NAME}.tenant
            SET {", ".join(updates)}
            WHERE id = %s
            RETURNING id, shortname, name, tenant_type, description,
                      is_active, created_at, metadata
            """,
            params,
        )
        row = await result.fetchone()
        await conn.commit()

    if not row:
        return None

    return TenantResponse(
        id=row[0],
        shortname=row[1],
        name=row[2],
        tenant_type=row[3],
        description=row[4],
        is_active=row[5],
        created_at=row[6],
        metadata=row[7],
    )
