"""Relation API endpoints."""

from fastapi import APIRouter, Header, HTTPException, Query

from mimir.schemas.relation import (
    RelationCreate,
    RelationListResponse,
    RelationResponse,
    RelationUpdate,
)
from mimir.services import relation_service

router = APIRouter(prefix="/relations", tags=["relations"])


@router.post("", response_model=RelationResponse, status_code=201)
async def create_relation(
    data: RelationCreate,
    x_tenant_id: int = Header(..., description="Tenant ID"),
) -> RelationResponse:
    """Create a new relation between entities."""
    return await relation_service.create_relation(x_tenant_id, data)


@router.get("", response_model=RelationListResponse)
async def list_relations(
    x_tenant_id: int = Header(..., description="Tenant ID"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    source_type: str | None = Query(None, description="Filter by source entity type"),
    source_id: int | None = Query(None, description="Filter by source entity ID"),
    target_type: str | None = Query(None, description="Filter by target entity type"),
    target_id: int | None = Query(None, description="Filter by target entity ID"),
    relation_type: str | None = Query(None, description="Filter by relation type"),
) -> RelationListResponse:
    """List relations for the tenant with pagination and filtering."""
    return await relation_service.list_relations(
        x_tenant_id,
        page,
        page_size,
        source_type,
        source_id,
        target_type,
        target_id,
        relation_type,
    )


@router.get("/entity/{entity_type}/{entity_id}", response_model=RelationListResponse)
async def list_entity_relations(
    entity_type: str,
    entity_id: int,
    x_tenant_id: int = Header(..., description="Tenant ID"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> RelationListResponse:
    """List all relations involving an entity (as source or target)."""
    return await relation_service.list_entity_relations(
        x_tenant_id, entity_type, entity_id, page, page_size
    )


@router.get("/{relation_id}", response_model=RelationResponse)
async def get_relation(
    relation_id: int,
    x_tenant_id: int = Header(..., description="Tenant ID"),
) -> RelationResponse:
    """Get relation by ID."""
    result = await relation_service.get_relation(relation_id, x_tenant_id)
    if not result:
        raise HTTPException(status_code=404, detail="Relation not found")
    return result


@router.patch("/{relation_id}", response_model=RelationResponse)
async def update_relation(
    relation_id: int,
    data: RelationUpdate,
    x_tenant_id: int = Header(..., description="Tenant ID"),
) -> RelationResponse:
    """Update relation."""
    result = await relation_service.update_relation(relation_id, x_tenant_id, data)
    if not result:
        raise HTTPException(status_code=404, detail="Relation not found")
    return result


@router.delete("/{relation_id}", status_code=204)
async def delete_relation(
    relation_id: int,
    x_tenant_id: int = Header(..., description="Tenant ID"),
) -> None:
    """Delete a relation."""
    deleted = await relation_service.delete_relation(relation_id, x_tenant_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Relation not found")
