"""Tenant service - database operations for tenants (V2).

V2.2 Changes (Phase 2):
- Joins tenant_type to expose deletion_policy on every tenant response
- get_deletion_policy() helper for artifact deletion enforcement
"""

from mimir.database import get_connection
from mimir.schemas.tenant import TenantCreate, TenantResponse, TenantUpdate

# Schema name for all tables
SCHEMA_NAME = "mimirdata"

# Column list shared across all tenant queries (joined with tenant_type for deletion_policy)
_TENANT_SELECT = f"""
    SELECT t.id, t.shortname, t.name, t.tenant_type, t.description,
           t.is_active, t.created_at, t.metadata,
           tt.deletion_policy
    FROM {SCHEMA_NAME}.tenant t
    JOIN {SCHEMA_NAME}.tenant_type tt ON tt.code = t.tenant_type
"""


async def create_tenant(data: TenantCreate) -> TenantResponse:
    """Create a new tenant."""
    async with get_connection() as conn:
        # Insert the tenant
        await conn.execute(
            f"""
            INSERT INTO {SCHEMA_NAME}.tenant
                (shortname, name, tenant_type, description, is_active, metadata)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                data.shortname,
                data.name,
                data.tenant_type,
                data.description,
                data.is_active,
                data.metadata,
            ),
        )
        await conn.commit()

        # Re-fetch with joined deletion_policy
        result = await conn.execute(
            _TENANT_SELECT + " WHERE t.shortname = %s",
            (data.shortname,),
        )
        row = await result.fetchone()

    return _row_to_tenant_response(row)


async def get_tenant(tenant_id: int) -> TenantResponse | None:
    """Get tenant by ID."""
    async with get_connection() as conn:
        result = await conn.execute(
            _TENANT_SELECT + " WHERE t.id = %s",
            (tenant_id,),
        )
        row = await result.fetchone()

    if not row:
        return None

    return _row_to_tenant_response(row)


async def get_tenant_by_shortname(shortname: str) -> TenantResponse | None:
    """Get tenant by shortname."""
    async with get_connection() as conn:
        result = await conn.execute(
            _TENANT_SELECT + " WHERE t.shortname = %s",
            (shortname,),
        )
        row = await result.fetchone()

    if not row:
        return None

    return _row_to_tenant_response(row)


async def list_tenants(active_only: bool = True) -> list[TenantResponse]:
    """List all tenants."""
    async with get_connection() as conn:
        query = _TENANT_SELECT
        if active_only:
            query += " WHERE t.is_active = true"
        query += " ORDER BY t.shortname"

        result = await conn.execute(query)
        rows = await result.fetchall()

    return [_row_to_tenant_response(row) for row in rows]


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
        await conn.execute(
            f"""
            UPDATE {SCHEMA_NAME}.tenant
            SET {", ".join(updates)}
            WHERE id = %s
            """,
            params,
        )
        await conn.commit()

    # Re-fetch with joined deletion_policy
    return await get_tenant(tenant_id)


async def get_deletion_policy(tenant_id: int) -> str | None:
    """Get the deletion policy for a tenant via its tenant type.

    Returns the policy string ('soft_delete', 'no_delete', 'physical_delete')
    or None if the tenant does not exist.
    """
    async with get_connection() as conn:
        result = await conn.execute(
            f"""
            SELECT tt.deletion_policy
            FROM {SCHEMA_NAME}.tenant t
            JOIN {SCHEMA_NAME}.tenant_type tt ON tt.code = t.tenant_type
            WHERE t.id = %s
            """,
            (tenant_id,),
        )
        row = await result.fetchone()

    return row[0] if row else None


def _row_to_tenant_response(row: tuple) -> TenantResponse:
    """Convert database row to TenantResponse.

    Row columns (9 total):
    0: id, 1: shortname, 2: name, 3: tenant_type, 4: description,
    5: is_active, 6: created_at, 7: metadata, 8: deletion_policy
    """
    return TenantResponse(
        id=row[0],
        shortname=row[1],
        name=row[2],
        tenant_type=row[3],
        description=row[4],
        is_active=row[5],
        created_at=row[6],
        metadata=row[7],
        deletion_policy=row[8],
    )
