"""Relation API endpoints (V2)."""

from fastapi import APIRouter, Header, HTTPException, Query

from mimir.schemas.relation import (
    EntityType,
    RelationCreate,
    RelationListResponse,
    RelationQueryParams,
    RelationResponse,
    RelationUpdate,
)
from mimir.services import relation_service

router = APIRouter(prefix="/relations", tags=["relations"])


@router.post("", response_model=RelationResponse, status_code=201)
async def create_relation(
    data: RelationCreate,
    x_tenant_id: int = Header(..., alias="X-Tenant-ID"),
) -> RelationResponse:
    """Create a new relation."""
    return await relation_service.create_relation(x_tenant_id, data)


@router.get("", response_model=RelationListResponse)
async def list_relations(
    x_tenant_id: int = Header(..., alias="X-Tenant-ID"),
    source_entity_type: EntityType | None = Query(None),
    source_entity_id: int | None = Query(None),
    target_entity_type: EntityType | None = Query(None),
    target_entity_id: int | None = Query(None),
    relation_type: str | None = Query(None),
) -> RelationListResponse:
    """List relations with optional filtering."""
    params = RelationQueryParams(
        source_entity_type=source_entity_type,
        source_entity_id=source_entity_id,
        target_entity_type=target_entity_type,
        target_entity_id=target_entity_id,
        relation_type=relation_type,
    )
    return await relation_service.list_relations(x_tenant_id, params)


@router.get("/{relation_id}", response_model=RelationResponse)
async def get_relation(
    relation_id: int,
    x_tenant_id: int = Header(..., alias="X-Tenant-ID"),
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
    x_tenant_id: int = Header(..., alias="X-Tenant-ID"),
) -> RelationResponse:
    """Update a relation."""
    result = await relation_service.update_relation(relation_id, x_tenant_id, data)
    if not result:
        raise HTTPException(status_code=404, detail="Relation not found")
    return result


@router.delete("/{relation_id}", status_code=204)
async def delete_relation(
    relation_id: int,
    x_tenant_id: int = Header(..., alias="X-Tenant-ID"),
) -> None:
    """Delete a relation."""
    deleted = await relation_service.delete_relation(relation_id, x_tenant_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Relation not found")


@router.get("/entity/{entity_type}/{entity_id}", response_model=list[RelationResponse])
async def get_entity_relations(
    entity_type: EntityType,
    entity_id: int,
    x_tenant_id: int = Header(..., alias="X-Tenant-ID"),
    as_source: bool = Query(True, description="Include relations where entity is source"),
    as_target: bool = Query(True, description="Include relations where entity is target"),
    relation_type: str | None = Query(None),
) -> list[RelationResponse]:
    """Get all relations for an entity."""
    return await relation_service.get_entity_relations(
        x_tenant_id, entity_type, entity_id, as_source, as_target, relation_type
    )
