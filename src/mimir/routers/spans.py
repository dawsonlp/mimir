"""Span API endpoints."""

from fastapi import APIRouter, Header, HTTPException, Query

from mimir.schemas.span import (
    SpanCreate,
    SpanListResponse,
    SpanResponse,
    SpanUpdate,
)
from mimir.services import span_service

router = APIRouter(prefix="/spans", tags=["spans"])


@router.post("", response_model=SpanResponse, status_code=201)
async def create_span(
    data: SpanCreate,
    x_tenant_id: int = Header(..., description="Tenant ID"),
) -> SpanResponse:
    """Create a new span."""
    return await span_service.create_span(x_tenant_id, data)


@router.get("", response_model=SpanListResponse)
async def list_spans(
    x_tenant_id: int = Header(..., description="Tenant ID"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    artifact_id: int | None = Query(None, description="Filter by artifact"),
    span_type: str | None = Query(None, description="Filter by span type"),
) -> SpanListResponse:
    """List spans for the tenant with pagination and filtering."""
    return await span_service.list_spans(
        x_tenant_id, page, page_size, artifact_id, span_type
    )


@router.get("/{span_id}", response_model=SpanResponse)
async def get_span(
    span_id: int,
    x_tenant_id: int = Header(..., description="Tenant ID"),
) -> SpanResponse:
    """Get span by ID."""
    result = await span_service.get_span(span_id, x_tenant_id)
    if not result:
        raise HTTPException(status_code=404, detail="Span not found")
    return result


@router.patch("/{span_id}", response_model=SpanResponse)
async def update_span(
    span_id: int,
    data: SpanUpdate,
    x_tenant_id: int = Header(..., description="Tenant ID"),
) -> SpanResponse:
    """Update span."""
    result = await span_service.update_span(span_id, x_tenant_id, data)
    if not result:
        raise HTTPException(status_code=404, detail="Span not found")
    return result


@router.delete("/{span_id}", status_code=204)
async def delete_span(
    span_id: int,
    x_tenant_id: int = Header(..., description="Tenant ID"),
) -> None:
    """Delete a span."""
    deleted = await span_service.delete_span(span_id, x_tenant_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Span not found")
