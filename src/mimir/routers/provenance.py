"""Provenance API endpoints for audit trail tracking."""

from datetime import datetime

from fastapi import APIRouter, Header, Query

from mimir.schemas.provenance import (
    EntityProvenanceResponse,
    ProvenanceEventCreate,
    ProvenanceEventListResponse,
    ProvenanceEventResponse,
)
from mimir.services import provenance_service

router = APIRouter(prefix="/provenance", tags=["provenance"])


@router.post("", response_model=ProvenanceEventResponse, status_code=201)
async def record_event(
    data: ProvenanceEventCreate,
    x_tenant_id: int = Header(..., description="Tenant ID"),
) -> ProvenanceEventResponse:
    """Record a provenance event.

    Provenance events are append-only and track who/what/when/why for entity changes.
    Use this endpoint to manually record audit events for operations not automatically
    tracked by the system.
    """
    return await provenance_service.record_event(x_tenant_id, data)


@router.get("", response_model=ProvenanceEventListResponse)
async def list_events(
    x_tenant_id: int = Header(..., description="Tenant ID"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=100, description="Items per page"),
    entity_type: str | None = Query(None, description="Filter by entity type"),
    action: str | None = Query(None, description="Filter by action type"),
    actor_type: str | None = Query(None, description="Filter by actor type"),
    actor_id: str | None = Query(None, description="Filter by actor ID"),
    start_time: datetime | None = Query(None, description="Filter events after this time"),  # noqa: B008
    end_time: datetime | None = Query(None, description="Filter events before this time"),  # noqa: B008
    correlation_id: str | None = Query(None, description="Filter by correlation ID"),
) -> ProvenanceEventListResponse:
    """List provenance events with pagination and filtering.

    Supports filtering by entity type, action, actor, time range, and correlation ID.
    Events are returned in reverse chronological order (most recent first).
    """
    return await provenance_service.list_events(
        x_tenant_id,
        page=page,
        page_size=page_size,
        entity_type=entity_type,
        action=action,
        actor_type=actor_type,
        actor_id=actor_id,
        start_time=start_time,
        end_time=end_time,
        correlation_id=correlation_id,
    )


@router.get("/entity/{entity_type}/{entity_id}", response_model=EntityProvenanceResponse)
async def get_entity_provenance(
    entity_type: str,
    entity_id: int,
    x_tenant_id: int = Header(..., description="Tenant ID"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=100, description="Items per page"),
) -> EntityProvenanceResponse:
    """Get provenance history for a specific entity.

    Returns all provenance events for the specified entity in reverse chronological
    order (most recent first). Use this to trace the complete audit trail for any
    entity in the system.

    Valid entity types: tenant, artifact, artifact_version, intent, intent_group,
    decision, span, relation, embedding
    """
    return await provenance_service.get_entity_provenance(
        x_tenant_id, entity_type, entity_id, page, page_size
    )


@router.get("/correlation/{correlation_id}", response_model=list[ProvenanceEventResponse])
async def get_correlated_events(
    correlation_id: str,
    x_tenant_id: int = Header(..., description="Tenant ID"),
) -> list[ProvenanceEventResponse]:
    """Get all events with the same correlation ID.

    Use this to trace related operations that span multiple entities.
    Events are returned in chronological order (oldest first) to show
    the sequence of operations.
    """
    return await provenance_service.get_correlated_events(x_tenant_id, correlation_id)
