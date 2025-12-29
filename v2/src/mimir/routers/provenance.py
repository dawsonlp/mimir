"""Provenance API endpoints (V2)."""

from datetime import datetime

from fastapi import APIRouter, Header, HTTPException, Query

from mimir.schemas.provenance import (
    ProvenanceAction,
    ProvenanceActorType,
    ProvenanceEventCreate,
    ProvenanceEventListResponse,
    ProvenanceEventResponse,
    ProvenanceQueryParams,
)
from mimir.schemas.relation import EntityType
from mimir.services import provenance_service

router = APIRouter(prefix="/provenance", tags=["provenance"])


@router.post("", response_model=ProvenanceEventResponse, status_code=201)
async def create_provenance_event(
    data: ProvenanceEventCreate,
    x_tenant_id: int = Header(..., alias="X-Tenant-ID"),
) -> ProvenanceEventResponse:
    """Create a new provenance event."""
    return await provenance_service.create_provenance_event(x_tenant_id, data)


@router.get("", response_model=ProvenanceEventListResponse)
async def list_provenance_events(
    x_tenant_id: int = Header(..., alias="X-Tenant-ID"),
    entity_type: EntityType | None = Query(None),
    entity_id: int | None = Query(None),
    action: ProvenanceAction | None = Query(None),
    actor_type: ProvenanceActorType | None = Query(None),
    actor_id: str | None = Query(None),
    since: datetime | None = Query(None),
    until: datetime | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> ProvenanceEventListResponse:
    """List provenance events with optional filtering."""
    params = ProvenanceQueryParams(
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        actor_type=actor_type,
        actor_id=actor_id,
        since=since,
        until=until,
    )
    return await provenance_service.list_provenance_events(
        x_tenant_id, params, limit, offset
    )


@router.get("/{event_id}", response_model=ProvenanceEventResponse)
async def get_provenance_event(
    event_id: int,
    x_tenant_id: int = Header(..., alias="X-Tenant-ID"),
) -> ProvenanceEventResponse:
    """Get provenance event by ID."""
    result = await provenance_service.get_provenance_event(event_id, x_tenant_id)
    if not result:
        raise HTTPException(status_code=404, detail="Provenance event not found")
    return result


@router.get(
    "/entity/{entity_type}/{entity_id}",
    response_model=list[ProvenanceEventResponse],
)
async def get_entity_history(
    entity_type: EntityType,
    entity_id: int,
    x_tenant_id: int = Header(..., alias="X-Tenant-ID"),
) -> list[ProvenanceEventResponse]:
    """Get full history for a specific entity."""
    return await provenance_service.get_entity_history(
        x_tenant_id, entity_type, entity_id
    )


@router.get("/actor/{actor_type}/{actor_id}", response_model=list[ProvenanceEventResponse])
async def get_actor_activity(
    actor_type: ProvenanceActorType,
    actor_id: str,
    x_tenant_id: int = Header(..., alias="X-Tenant-ID"),
    since: datetime | None = Query(None),
    until: datetime | None = Query(None),
) -> list[ProvenanceEventResponse]:
    """Get all activity by a specific actor."""
    return await provenance_service.get_actor_activity(
        x_tenant_id, actor_type, actor_id, since, until
    )
