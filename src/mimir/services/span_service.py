"""Span service - database operations for spans."""

from mimir.database import get_connection
from mimir.models import SCHEMA_NAME
from mimir.schemas.span import (
    SpanCreate,
    SpanListResponse,
    SpanResponse,
    SpanUpdate,
)


async def create_span(tenant_id: int, data: SpanCreate) -> SpanResponse:
    """Create a new span."""
    async with get_connection() as conn:
        result = await conn.execute(
            f"""
            INSERT INTO {SCHEMA_NAME}.spans
                (tenant_id, artifact_id, artifact_version_id, span_type,
                 start_offset, end_offset, content, annotation, metadata)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id, tenant_id, artifact_id, artifact_version_id, span_type,
                      start_offset, end_offset, content, annotation,
                      created_at, updated_at, metadata
            """,
            (
                tenant_id,
                data.artifact_id,
                data.artifact_version_id,
                data.span_type.value,
                data.start_offset,
                data.end_offset,
                data.content,
                data.annotation,
                data.metadata,
            ),
        )
        row = await result.fetchone()
        await conn.commit()

    return SpanResponse(
        id=row[0],
        tenant_id=row[1],
        artifact_id=row[2],
        artifact_version_id=row[3],
        span_type=row[4],
        start_offset=row[5],
        end_offset=row[6],
        content=row[7],
        annotation=row[8],
        created_at=row[9],
        updated_at=row[10],
        metadata=row[11],
    )


async def get_span(span_id: int, tenant_id: int) -> SpanResponse | None:
    """Get span by ID."""
    async with get_connection() as conn:
        result = await conn.execute(
            f"""
            SELECT id, tenant_id, artifact_id, artifact_version_id, span_type,
                   start_offset, end_offset, content, annotation,
                   created_at, updated_at, metadata
            FROM {SCHEMA_NAME}.spans
            WHERE id = %s AND tenant_id = %s
            """,
            (span_id, tenant_id),
        )
        row = await result.fetchone()

    if not row:
        return None

    return SpanResponse(
        id=row[0],
        tenant_id=row[1],
        artifact_id=row[2],
        artifact_version_id=row[3],
        span_type=row[4],
        start_offset=row[5],
        end_offset=row[6],
        content=row[7],
        annotation=row[8],
        created_at=row[9],
        updated_at=row[10],
        metadata=row[11],
    )


async def list_spans(
    tenant_id: int,
    page: int = 1,
    page_size: int = 20,
    artifact_id: int | None = None,
    span_type: str | None = None,
) -> SpanListResponse:
    """List spans for a tenant with pagination and filtering."""
    offset = (page - 1) * page_size

    async with get_connection() as conn:
        # Build query with optional filters
        where_clause = "WHERE tenant_id = %s"
        params: list = [tenant_id]

        if artifact_id is not None:
            where_clause += " AND artifact_id = %s"
            params.append(artifact_id)
        if span_type:
            where_clause += " AND span_type = %s"
            params.append(span_type)

        # Get total count
        count_result = await conn.execute(
            f"SELECT COUNT(*) FROM {SCHEMA_NAME}.spans {where_clause}",
            params,
        )
        total = (await count_result.fetchone())[0]

        # Get page of spans
        result = await conn.execute(
            f"""
            SELECT id, tenant_id, artifact_id, artifact_version_id, span_type,
                   start_offset, end_offset, content, annotation,
                   created_at, updated_at, metadata
            FROM {SCHEMA_NAME}.spans
            {where_clause}
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
            """,
            params + [page_size, offset],
        )
        rows = await result.fetchall()

    items = [
        SpanResponse(
            id=row[0],
            tenant_id=row[1],
            artifact_id=row[2],
            artifact_version_id=row[3],
            span_type=row[4],
            start_offset=row[5],
            end_offset=row[6],
            content=row[7],
            annotation=row[8],
            created_at=row[9],
            updated_at=row[10],
            metadata=row[11],
        )
        for row in rows
    ]

    return SpanListResponse(
        items=items, total=total, page=page, page_size=page_size
    )


async def update_span(
    span_id: int, tenant_id: int, data: SpanUpdate
) -> SpanResponse | None:
    """Update span."""
    updates = []
    params = []

    if data.span_type is not None:
        updates.append("span_type = %s")
        params.append(data.span_type.value)
    if data.start_offset is not None:
        updates.append("start_offset = %s")
        params.append(data.start_offset)
    if data.end_offset is not None:
        updates.append("end_offset = %s")
        params.append(data.end_offset)
    if data.content is not None:
        updates.append("content = %s")
        params.append(data.content)
    if data.annotation is not None:
        updates.append("annotation = %s")
        params.append(data.annotation)
    if data.metadata is not None:
        updates.append("metadata = %s")
        params.append(data.metadata)

    if not updates:
        return await get_span(span_id, tenant_id)

    params.extend([span_id, tenant_id])

    async with get_connection() as conn:
        result = await conn.execute(
            f"""
            UPDATE {SCHEMA_NAME}.spans
            SET {", ".join(updates)}
            WHERE id = %s AND tenant_id = %s
            RETURNING id, tenant_id, artifact_id, artifact_version_id, span_type,
                      start_offset, end_offset, content, annotation,
                      created_at, updated_at, metadata
            """,
            params,
        )
        row = await result.fetchone()
        await conn.commit()

    if not row:
        return None

    return SpanResponse(
        id=row[0],
        tenant_id=row[1],
        artifact_id=row[2],
        artifact_version_id=row[3],
        span_type=row[4],
        start_offset=row[5],
        end_offset=row[6],
        content=row[7],
        annotation=row[8],
        created_at=row[9],
        updated_at=row[10],
        metadata=row[11],
    )


async def delete_span(span_id: int, tenant_id: int) -> bool:
    """Delete a span."""
    async with get_connection() as conn:
        result = await conn.execute(
            f"""
            DELETE FROM {SCHEMA_NAME}.spans
            WHERE id = %s AND tenant_id = %s
            RETURNING id
            """,
            (span_id, tenant_id),
        )
        row = await result.fetchone()
        await conn.commit()

    return row is not None
