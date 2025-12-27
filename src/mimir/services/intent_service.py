"""Intent service - database operations for intents and intent groups."""

from datetime import UTC, datetime

from mimir.database import get_connection
from mimir.models import SCHEMA_NAME
from mimir.schemas.intent import (
    IntentCreate,
    IntentGroupCreate,
    IntentGroupListResponse,
    IntentGroupResponse,
    IntentGroupUpdate,
    IntentListResponse,
    IntentResponse,
    IntentUpdate,
)

# ============================================================================
# Intent Group Operations
# ============================================================================


async def create_intent_group(
    tenant_id: int, data: IntentGroupCreate
) -> IntentGroupResponse:
    """Create a new intent group."""
    async with get_connection() as conn:
        result = await conn.execute(
            f"""
            INSERT INTO {SCHEMA_NAME}.intent_groups
                (tenant_id, name, description, metadata)
            VALUES (%s, %s, %s, %s)
            RETURNING id, tenant_id, name, description, metadata, created_at, updated_at
            """,
            (tenant_id, data.name, data.description, data.metadata),
        )
        row = await result.fetchone()
        await conn.commit()

    return IntentGroupResponse(
        id=row[0],
        tenant_id=row[1],
        name=row[2],
        description=row[3],
        metadata=row[4],
        created_at=row[5],
        updated_at=row[6],
    )


async def get_intent_group(
    group_id: int, tenant_id: int
) -> IntentGroupResponse | None:
    """Get intent group by ID."""
    async with get_connection() as conn:
        result = await conn.execute(
            f"""
            SELECT id, tenant_id, name, description, metadata, created_at, updated_at
            FROM {SCHEMA_NAME}.intent_groups
            WHERE id = %s AND tenant_id = %s
            """,
            (group_id, tenant_id),
        )
        row = await result.fetchone()

    if not row:
        return None

    return IntentGroupResponse(
        id=row[0],
        tenant_id=row[1],
        name=row[2],
        description=row[3],
        metadata=row[4],
        created_at=row[5],
        updated_at=row[6],
    )


async def list_intent_groups(
    tenant_id: int,
    page: int = 1,
    page_size: int = 20,
) -> IntentGroupListResponse:
    """List intent groups for a tenant with pagination."""
    offset = (page - 1) * page_size

    async with get_connection() as conn:
        # Get total count
        count_result = await conn.execute(
            f"SELECT COUNT(*) FROM {SCHEMA_NAME}.intent_groups WHERE tenant_id = %s",
            (tenant_id,),
        )
        total = (await count_result.fetchone())[0]

        # Get page of groups
        result = await conn.execute(
            f"""
            SELECT id, tenant_id, name, description, metadata, created_at, updated_at
            FROM {SCHEMA_NAME}.intent_groups
            WHERE tenant_id = %s
            ORDER BY name ASC
            LIMIT %s OFFSET %s
            """,
            (tenant_id, page_size, offset),
        )
        rows = await result.fetchall()

    items = [
        IntentGroupResponse(
            id=row[0],
            tenant_id=row[1],
            name=row[2],
            description=row[3],
            metadata=row[4],
            created_at=row[5],
            updated_at=row[6],
        )
        for row in rows
    ]

    return IntentGroupListResponse(
        items=items, total=total, page=page, page_size=page_size
    )


async def update_intent_group(
    group_id: int, tenant_id: int, data: IntentGroupUpdate
) -> IntentGroupResponse | None:
    """Update intent group."""
    updates = []
    params = []

    if data.name is not None:
        updates.append("name = %s")
        params.append(data.name)
    if data.description is not None:
        updates.append("description = %s")
        params.append(data.description)
    if data.metadata is not None:
        updates.append("metadata = %s")
        params.append(data.metadata)

    if not updates:
        return await get_intent_group(group_id, tenant_id)

    params.extend([group_id, tenant_id])

    async with get_connection() as conn:
        result = await conn.execute(
            f"""
            UPDATE {SCHEMA_NAME}.intent_groups
            SET {", ".join(updates)}
            WHERE id = %s AND tenant_id = %s
            RETURNING id, tenant_id, name, description, metadata, created_at, updated_at
            """,
            params,
        )
        row = await result.fetchone()
        await conn.commit()

    if not row:
        return None

    return IntentGroupResponse(
        id=row[0],
        tenant_id=row[1],
        name=row[2],
        description=row[3],
        metadata=row[4],
        created_at=row[5],
        updated_at=row[6],
    )


async def delete_intent_group(group_id: int, tenant_id: int) -> bool:
    """Delete an intent group."""
    async with get_connection() as conn:
        result = await conn.execute(
            f"""
            DELETE FROM {SCHEMA_NAME}.intent_groups
            WHERE id = %s AND tenant_id = %s
            RETURNING id
            """,
            (group_id, tenant_id),
        )
        row = await result.fetchone()
        await conn.commit()

    return row is not None


# ============================================================================
# Intent Operations
# ============================================================================


async def create_intent(tenant_id: int, data: IntentCreate) -> IntentResponse:
    """Create a new intent."""
    async with get_connection() as conn:
        result = await conn.execute(
            f"""
            INSERT INTO {SCHEMA_NAME}.intents
                (tenant_id, intent_group_id, artifact_id, title, description,
                 status, source, metadata)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id, tenant_id, intent_group_id, artifact_id, title, description,
                      status, source, created_at, updated_at, resolved_at, metadata
            """,
            (
                tenant_id,
                data.intent_group_id,
                data.artifact_id,
                data.title,
                data.description,
                "active",  # New intents always start active
                data.source.value,
                data.metadata,
            ),
        )
        row = await result.fetchone()
        await conn.commit()

    return IntentResponse(
        id=row[0],
        tenant_id=row[1],
        intent_group_id=row[2],
        artifact_id=row[3],
        title=row[4],
        description=row[5],
        status=row[6],
        source=row[7],
        created_at=row[8],
        updated_at=row[9],
        resolved_at=row[10],
        metadata=row[11],
    )


async def get_intent(intent_id: int, tenant_id: int) -> IntentResponse | None:
    """Get intent by ID."""
    async with get_connection() as conn:
        result = await conn.execute(
            f"""
            SELECT id, tenant_id, intent_group_id, artifact_id, title, description,
                   status, source, created_at, updated_at, resolved_at, metadata
            FROM {SCHEMA_NAME}.intents
            WHERE id = %s AND tenant_id = %s
            """,
            (intent_id, tenant_id),
        )
        row = await result.fetchone()

    if not row:
        return None

    return IntentResponse(
        id=row[0],
        tenant_id=row[1],
        intent_group_id=row[2],
        artifact_id=row[3],
        title=row[4],
        description=row[5],
        status=row[6],
        source=row[7],
        created_at=row[8],
        updated_at=row[9],
        resolved_at=row[10],
        metadata=row[11],
    )


async def list_intents(
    tenant_id: int,
    page: int = 1,
    page_size: int = 20,
    status: str | None = None,
    intent_group_id: int | None = None,
) -> IntentListResponse:
    """List intents for a tenant with pagination and filtering."""
    offset = (page - 1) * page_size

    async with get_connection() as conn:
        # Build query with optional filters
        where_clause = "WHERE tenant_id = %s"
        params: list = [tenant_id]

        if status:
            where_clause += " AND status = %s"
            params.append(status)
        if intent_group_id is not None:
            where_clause += " AND intent_group_id = %s"
            params.append(intent_group_id)

        # Get total count
        count_result = await conn.execute(
            f"SELECT COUNT(*) FROM {SCHEMA_NAME}.intents {where_clause}",
            params,
        )
        total = (await count_result.fetchone())[0]

        # Get page of intents
        result = await conn.execute(
            f"""
            SELECT id, tenant_id, intent_group_id, artifact_id, title, description,
                   status, source, created_at, updated_at, resolved_at, metadata
            FROM {SCHEMA_NAME}.intents
            {where_clause}
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
            """,
            params + [page_size, offset],
        )
        rows = await result.fetchall()

    items = [
        IntentResponse(
            id=row[0],
            tenant_id=row[1],
            intent_group_id=row[2],
            artifact_id=row[3],
            title=row[4],
            description=row[5],
            status=row[6],
            source=row[7],
            created_at=row[8],
            updated_at=row[9],
            resolved_at=row[10],
            metadata=row[11],
        )
        for row in rows
    ]

    return IntentListResponse(
        items=items, total=total, page=page, page_size=page_size
    )


async def update_intent(
    intent_id: int, tenant_id: int, data: IntentUpdate
) -> IntentResponse | None:
    """Update intent."""
    updates = []
    params = []

    if data.title is not None:
        updates.append("title = %s")
        params.append(data.title)
    if data.description is not None:
        updates.append("description = %s")
        params.append(data.description)
    if data.intent_group_id is not None:
        updates.append("intent_group_id = %s")
        params.append(data.intent_group_id)
    if data.status is not None:
        updates.append("status = %s")
        params.append(data.status.value)
        # Set resolved_at when status changes to resolved
        if data.status.value == "resolved":
            updates.append("resolved_at = %s")
            params.append(datetime.now(UTC))
    if data.metadata is not None:
        updates.append("metadata = %s")
        params.append(data.metadata)

    if not updates:
        return await get_intent(intent_id, tenant_id)

    params.extend([intent_id, tenant_id])

    async with get_connection() as conn:
        result = await conn.execute(
            f"""
            UPDATE {SCHEMA_NAME}.intents
            SET {", ".join(updates)}
            WHERE id = %s AND tenant_id = %s
            RETURNING id, tenant_id, intent_group_id, artifact_id, title, description,
                      status, source, created_at, updated_at, resolved_at, metadata
            """,
            params,
        )
        row = await result.fetchone()
        await conn.commit()

    if not row:
        return None

    return IntentResponse(
        id=row[0],
        tenant_id=row[1],
        intent_group_id=row[2],
        artifact_id=row[3],
        title=row[4],
        description=row[5],
        status=row[6],
        source=row[7],
        created_at=row[8],
        updated_at=row[9],
        resolved_at=row[10],
        metadata=row[11],
    )


async def delete_intent(intent_id: int, tenant_id: int) -> bool:
    """Delete an intent."""
    async with get_connection() as conn:
        result = await conn.execute(
            f"""
            DELETE FROM {SCHEMA_NAME}.intents
            WHERE id = %s AND tenant_id = %s
            RETURNING id
            """,
            (intent_id, tenant_id),
        )
        row = await result.fetchone()
        await conn.commit()

    return row is not None
