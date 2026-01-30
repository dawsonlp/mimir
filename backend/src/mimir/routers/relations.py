"""Relation API endpoints (V2 append-only).

V2 Changes:
- UUID path parameters (not INT)
- UUID references to artifacts (not entity_type/entity_id INT)
- No PATCH/UPDATE endpoint (append-only)
- No DELETE endpoint (append-only)
- 409 Conflict on duplicate relation
"""

from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Query

from mimir.schemas.relation import (
    RelationCreate,
    RelationListResponse,
    RelationResponse,
)
from mimir.services import relation_service

router = APIRouter(prefix="/relations", tags=["relations"])


@router.post("", response_model=RelationResponse, status_code=201)
async def create_relation(
    data: RelationCreate,
    x_tenant_id: int = Header(..., alias="X-Tenant-ID"),
) -> RelationResponse:
    """Create a new relation.
    
    If `id` is provided in the request body, uses that UUID.
    If omitted, server generates a UUID.
    Returns 409 Conflict if the relation already exists (same source, target, type).
    """
    result = await relation_service.create_relation(x_tenant_id, data)
    if result is None:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Relation already exists",
                "source_id": str(data.source_id),
                "target_id": str(data.target_id),
                "relation_type": data.relation_type,
            },
        )
    return result


@router.get("", response_model=RelationListResponse)
async def list_relations(
    x_tenant_id: int = Header(..., alias="X-Tenant-ID"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    source_id: UUID | None = Query(None),
    target_id: UUID | None = Query(None),
    relation_type: str | None = Query(None),
) -> RelationListResponse:
    """List relations with optional filtering."""
    return await relation_service.list_relations(
        x_tenant_id, limit, offset, source_id, target_id, relation_type
    )


@router.get("/{relation_id}", response_model=RelationResponse)
async def get_relation(
    relation_id: UUID,
    x_tenant_id: int = Header(..., alias="X-Tenant-ID"),
) -> RelationResponse:
    """Get relation by UUID."""
    result = await relation_service.get_relation(relation_id, x_tenant_id)
    if not result:
        raise HTTPException(status_code=404, detail="Relation not found")
    return result


@router.get("/artifact/{artifact_id}", response_model=list[RelationResponse])
async def get_artifact_relations(
    artifact_id: UUID,
    x_tenant_id: int = Header(..., alias="X-Tenant-ID"),
    as_source: bool = Query(True, description="Include relations where artifact is source"),
    as_target: bool = Query(True, description="Include relations where artifact is target"),
    relation_type: str | None = Query(None),
) -> list[RelationResponse]:
    """Get all relations for an artifact."""
    return await relation_service.get_artifact_relations(
        x_tenant_id, artifact_id, as_source, as_target, relation_type
    )


# NOTE: PATCH/UPDATE endpoint removed - relations are append-only
# NOTE: DELETE endpoint removed - relations are append-only
