"""Artifact API endpoints."""

from fastapi import APIRouter, Header, HTTPException, Query

from mimir.schemas.artifact import (
    ArtifactCreate,
    ArtifactDetailResponse,
    ArtifactListResponse,
    ArtifactResponse,
    ArtifactUpdate,
    ArtifactVersionCreate,
    ArtifactVersionResponse,
)
from mimir.services import artifact_service

router = APIRouter(prefix="/artifacts", tags=["artifacts"])


def _get_tenant_id(x_tenant_id: int = Header(..., description="Tenant ID")) -> int:
    """Extract tenant ID from header."""
    return x_tenant_id


@router.post("", response_model=ArtifactDetailResponse, status_code=201)
async def create_artifact(
    data: ArtifactCreate,
    x_tenant_id: int = Header(..., description="Tenant ID"),
) -> ArtifactDetailResponse:
    """Create a new artifact with initial content version."""
    return await artifact_service.create_artifact(x_tenant_id, data)


@router.get("", response_model=ArtifactListResponse)
async def list_artifacts(
    x_tenant_id: int = Header(..., description="Tenant ID"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    artifact_type: str | None = Query(None),
) -> ArtifactListResponse:
    """List artifacts for the tenant with pagination."""
    return await artifact_service.list_artifacts(
        x_tenant_id, page, page_size, artifact_type
    )


@router.get("/{artifact_id}", response_model=ArtifactDetailResponse)
async def get_artifact(
    artifact_id: int,
    x_tenant_id: int = Header(..., description="Tenant ID"),
) -> ArtifactDetailResponse:
    """Get artifact by ID with latest version."""
    result = await artifact_service.get_artifact(artifact_id, x_tenant_id)
    if not result:
        raise HTTPException(status_code=404, detail="Artifact not found")
    return result


@router.patch("/{artifact_id}", response_model=ArtifactResponse)
async def update_artifact(
    artifact_id: int,
    data: ArtifactUpdate,
    x_tenant_id: int = Header(..., description="Tenant ID"),
) -> ArtifactResponse:
    """Update artifact metadata."""
    result = await artifact_service.update_artifact(artifact_id, x_tenant_id, data)
    if not result:
        raise HTTPException(status_code=404, detail="Artifact not found")
    return result


@router.delete("/{artifact_id}", status_code=204)
async def delete_artifact(
    artifact_id: int,
    x_tenant_id: int = Header(..., description="Tenant ID"),
) -> None:
    """Delete an artifact and all its versions."""
    deleted = await artifact_service.delete_artifact(artifact_id, x_tenant_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Artifact not found")


@router.post(
    "/{artifact_id}/versions",
    response_model=ArtifactVersionResponse,
    status_code=201,
)
async def add_version(
    artifact_id: int,
    data: ArtifactVersionCreate,
    x_tenant_id: int = Header(..., description="Tenant ID"),
) -> ArtifactVersionResponse:
    """Add a new version to an artifact."""
    result = await artifact_service.add_version(artifact_id, x_tenant_id, data)
    if not result:
        raise HTTPException(status_code=404, detail="Artifact not found")
    return result


@router.get(
    "/{artifact_id}/versions",
    response_model=list[ArtifactVersionResponse],
)
async def get_versions(
    artifact_id: int,
    x_tenant_id: int = Header(..., description="Tenant ID"),
) -> list[ArtifactVersionResponse]:
    """Get all versions of an artifact."""
    return await artifact_service.get_versions(artifact_id, x_tenant_id)
