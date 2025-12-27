"""Decision service - database operations for decisions."""

from mimir.database import get_connection
from mimir.models import SCHEMA_NAME
from mimir.schemas.decision import (
    DecisionCreate,
    DecisionListResponse,
    DecisionResponse,
    DecisionSupersede,
    DecisionUpdate,
)


async def create_decision(tenant_id: int, data: DecisionCreate) -> DecisionResponse:
    """Create a new decision."""
    async with get_connection() as conn:
        result = await conn.execute(
            f"""
            INSERT INTO {SCHEMA_NAME}.decisions
                (tenant_id, artifact_id, intent_id, statement, rationale,
                 status, source, metadata)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id, tenant_id, artifact_id, intent_id, statement, rationale,
                      status, source, superseded_by_id, created_at, updated_at, metadata
            """,
            (
                tenant_id,
                data.artifact_id,
                data.intent_id,
                data.statement,
                data.rationale,
                data.status.value,
                data.source.value,
                data.metadata,
            ),
        )
        row = await result.fetchone()
        await conn.commit()

    return DecisionResponse(
        id=row[0],
        tenant_id=row[1],
        artifact_id=row[2],
        intent_id=row[3],
        statement=row[4],
        rationale=row[5],
        status=row[6],
        source=row[7],
        superseded_by_id=row[8],
        created_at=row[9],
        updated_at=row[10],
        metadata=row[11],
    )


async def get_decision(decision_id: int, tenant_id: int) -> DecisionResponse | None:
    """Get decision by ID."""
    async with get_connection() as conn:
        result = await conn.execute(
            f"""
            SELECT id, tenant_id, artifact_id, intent_id, statement, rationale,
                   status, source, superseded_by_id, created_at, updated_at, metadata
            FROM {SCHEMA_NAME}.decisions
            WHERE id = %s AND tenant_id = %s
            """,
            (decision_id, tenant_id),
        )
        row = await result.fetchone()

    if not row:
        return None

    return DecisionResponse(
        id=row[0],
        tenant_id=row[1],
        artifact_id=row[2],
        intent_id=row[3],
        statement=row[4],
        rationale=row[5],
        status=row[6],
        source=row[7],
        superseded_by_id=row[8],
        created_at=row[9],
        updated_at=row[10],
        metadata=row[11],
    )


async def list_decisions(
    tenant_id: int,
    page: int = 1,
    page_size: int = 20,
    status: str | None = None,
    intent_id: int | None = None,
    artifact_id: int | None = None,
) -> DecisionListResponse:
    """List decisions for a tenant with pagination and filtering."""
    offset = (page - 1) * page_size

    async with get_connection() as conn:
        # Build query with optional filters
        where_clause = "WHERE tenant_id = %s"
        params: list = [tenant_id]

        if status:
            where_clause += " AND status = %s"
            params.append(status)
        if intent_id is not None:
            where_clause += " AND intent_id = %s"
            params.append(intent_id)
        if artifact_id is not None:
            where_clause += " AND artifact_id = %s"
            params.append(artifact_id)

        # Get total count
        count_result = await conn.execute(
            f"SELECT COUNT(*) FROM {SCHEMA_NAME}.decisions {where_clause}",
            params,
        )
        total = (await count_result.fetchone())[0]

        # Get page of decisions
        result = await conn.execute(
            f"""
            SELECT id, tenant_id, artifact_id, intent_id, statement, rationale,
                   status, source, superseded_by_id, created_at, updated_at, metadata
            FROM {SCHEMA_NAME}.decisions
            {where_clause}
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
            """,
            params + [page_size, offset],
        )
        rows = await result.fetchall()

    items = [
        DecisionResponse(
            id=row[0],
            tenant_id=row[1],
            artifact_id=row[2],
            intent_id=row[3],
            statement=row[4],
            rationale=row[5],
            status=row[6],
            source=row[7],
            superseded_by_id=row[8],
            created_at=row[9],
            updated_at=row[10],
            metadata=row[11],
        )
        for row in rows
    ]

    return DecisionListResponse(
        items=items, total=total, page=page, page_size=page_size
    )


async def update_decision(
    decision_id: int, tenant_id: int, data: DecisionUpdate
) -> DecisionResponse | None:
    """Update decision."""
    updates = []
    params = []

    if data.statement is not None:
        updates.append("statement = %s")
        params.append(data.statement)
    if data.rationale is not None:
        updates.append("rationale = %s")
        params.append(data.rationale)
    if data.status is not None:
        updates.append("status = %s")
        params.append(data.status.value)
    if data.metadata is not None:
        updates.append("metadata = %s")
        params.append(data.metadata)

    if not updates:
        return await get_decision(decision_id, tenant_id)

    params.extend([decision_id, tenant_id])

    async with get_connection() as conn:
        result = await conn.execute(
            f"""
            UPDATE {SCHEMA_NAME}.decisions
            SET {", ".join(updates)}
            WHERE id = %s AND tenant_id = %s
            RETURNING id, tenant_id, artifact_id, intent_id, statement, rationale,
                      status, source, superseded_by_id, created_at, updated_at, metadata
            """,
            params,
        )
        row = await result.fetchone()
        await conn.commit()

    if not row:
        return None

    return DecisionResponse(
        id=row[0],
        tenant_id=row[1],
        artifact_id=row[2],
        intent_id=row[3],
        statement=row[4],
        rationale=row[5],
        status=row[6],
        source=row[7],
        superseded_by_id=row[8],
        created_at=row[9],
        updated_at=row[10],
        metadata=row[11],
    )


async def supersede_decision(
    decision_id: int, tenant_id: int, data: DecisionSupersede
) -> tuple[DecisionResponse, DecisionResponse] | None:
    """Supersede a decision with a new one.

    Creates a new decision and marks the old one as superseded.
    Returns tuple of (old_decision, new_decision) or None if not found.
    """
    async with get_connection() as conn:
        # Verify original decision exists and belongs to tenant
        check = await conn.execute(
            f"""
            SELECT id, artifact_id, intent_id, source
            FROM {SCHEMA_NAME}.decisions
            WHERE id = %s AND tenant_id = %s
            """,
            (decision_id, tenant_id),
        )
        old_row = await check.fetchone()
        if not old_row:
            return None

        # Create new decision inheriting context from old one
        new_result = await conn.execute(
            f"""
            INSERT INTO {SCHEMA_NAME}.decisions
                (tenant_id, artifact_id, intent_id, statement, rationale,
                 status, source, metadata)
            VALUES (%s, %s, %s, %s, %s, 'active', %s, %s)
            RETURNING id, tenant_id, artifact_id, intent_id, statement, rationale,
                      status, source, superseded_by_id, created_at, updated_at, metadata
            """,
            (
                tenant_id,
                old_row[1],  # artifact_id
                old_row[2],  # intent_id
                data.new_statement,
                data.new_rationale,
                old_row[3],  # source - inherit from original
                data.metadata,
            ),
        )
        new_row = await new_result.fetchone()

        # Update old decision to superseded and link to new one
        old_result = await conn.execute(
            f"""
            UPDATE {SCHEMA_NAME}.decisions
            SET status = 'superseded', superseded_by_id = %s
            WHERE id = %s AND tenant_id = %s
            RETURNING id, tenant_id, artifact_id, intent_id, statement, rationale,
                      status, source, superseded_by_id, created_at, updated_at, metadata
            """,
            (new_row[0], decision_id, tenant_id),
        )
        updated_old_row = await old_result.fetchone()
        await conn.commit()

    old_decision = DecisionResponse(
        id=updated_old_row[0],
        tenant_id=updated_old_row[1],
        artifact_id=updated_old_row[2],
        intent_id=updated_old_row[3],
        statement=updated_old_row[4],
        rationale=updated_old_row[5],
        status=updated_old_row[6],
        source=updated_old_row[7],
        superseded_by_id=updated_old_row[8],
        created_at=updated_old_row[9],
        updated_at=updated_old_row[10],
        metadata=updated_old_row[11],
    )

    new_decision = DecisionResponse(
        id=new_row[0],
        tenant_id=new_row[1],
        artifact_id=new_row[2],
        intent_id=new_row[3],
        statement=new_row[4],
        rationale=new_row[5],
        status=new_row[6],
        source=new_row[7],
        superseded_by_id=new_row[8],
        created_at=new_row[9],
        updated_at=new_row[10],
        metadata=new_row[11],
    )

    return (old_decision, new_decision)


async def delete_decision(decision_id: int, tenant_id: int) -> bool:
    """Delete a decision."""
    async with get_connection() as conn:
        result = await conn.execute(
            f"""
            DELETE FROM {SCHEMA_NAME}.decisions
            WHERE id = %s AND tenant_id = %s
            RETURNING id
            """,
            (decision_id, tenant_id),
        )
        row = await result.fetchone()
        await conn.commit()

    return row is not None
