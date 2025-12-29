"""Artifact type vocabulary API endpoints (V2 - NEW)."""

from fastapi import APIRouter, HTTPException, Query

from mimir.schemas.artifact_type import (
    ArtifactTypeCreate,
    ArtifactTypeListResponse,
    ArtifactTypeResponse,
    ArtifactTypeUpdate,
)
from mimir.services import artifact_type_service

router = APIRouter(prefix="/artifact-types", tags=["artifact-types"])


@router.post("", response_model=ArtifactTypeResponse, status_code=201)
async def create_artifact_type(data: ArtifactTypeCreate) -> ArtifactTypeResponse:
    """Create a new artifact type."""
    return await artifact_type_service.create_artifact_type(data)


@router.get("", response_model=ArtifactTypeListResponse)
async def list_artifact_types(
    active_only: bool = Query(True, description="Only show active types"),
    category: str | None = Query(None, description="Filter by category"),
) -> ArtifactTypeListResponse:
    """List all artifact types."""
    types = await artifact_type_service.list_artifact_types(active_only, category)
    return ArtifactTypeListResponse(items=types, total=len(types))


@router.get("/{code}", response_model=ArtifactTypeResponse)
async def get_artifact_type(code: str) -> ArtifactTypeResponse:
    """Get artifact type by code."""
    result = await artifact_type_service.get_artifact_type(code)
    if not result:
        raise HTTPException(status_code=404, detail="Artifact type not found")
    return result


@router.patch("/{code}", response_model=ArtifactTypeResponse)
async def update_artifact_type(
    code: str, data: ArtifactTypeUpdate
) -> ArtifactTypeResponse:
    """Update an artifact type."""
    result = await artifact_type_service.update_artifact_type(code, data)
    if not result:
        raise HTTPException(status_code=404, detail="Artifact type not found")
    return result
