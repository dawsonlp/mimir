"""Relation type vocabulary API endpoints (V2 - NEW)."""

from fastapi import APIRouter, HTTPException, Query

from mimir.schemas.relation_type import (
    RelationTypeCreate,
    RelationTypeListResponse,
    RelationTypeResponse,
    RelationTypeUpdate,
)
from mimir.services import relation_type_service

router = APIRouter(prefix="/relation-types", tags=["relation-types"])


@router.post("", response_model=RelationTypeResponse, status_code=201)
async def create_relation_type(data: RelationTypeCreate) -> RelationTypeResponse:
    """Create a new relation type."""
    return await relation_type_service.create_relation_type(data)


@router.get("", response_model=RelationTypeListResponse)
async def list_relation_types(
    active_only: bool = Query(True, description="Only show active types"),
) -> RelationTypeListResponse:
    """List all relation types."""
    types = await relation_type_service.list_relation_types(active_only)
    return RelationTypeListResponse(items=types, total=len(types))


@router.get("/{code}", response_model=RelationTypeResponse)
async def get_relation_type(code: str) -> RelationTypeResponse:
    """Get relation type by code."""
    result = await relation_type_service.get_relation_type(code)
    if not result:
        raise HTTPException(status_code=404, detail="Relation type not found")
    return result


@router.get("/{code}/inverse", response_model=RelationTypeResponse)
async def get_inverse_relation_type(code: str) -> RelationTypeResponse:
    """Get the inverse relation type."""
    result = await relation_type_service.get_inverse_type(code)
    if not result:
        raise HTTPException(status_code=404, detail="No inverse relation type defined")
    return result


@router.patch("/{code}", response_model=RelationTypeResponse)
async def update_relation_type(
    code: str, data: RelationTypeUpdate
) -> RelationTypeResponse:
    """Update a relation type."""
    result = await relation_type_service.update_relation_type(code, data)
    if not result:
        raise HTTPException(status_code=404, detail="Relation type not found")
    return result
