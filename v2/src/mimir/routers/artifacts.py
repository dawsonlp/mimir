"""Artifact API endpoints (V2)."""

from fastapi import APIRouter, Header, HTTPException, Query

from mimir.schemas.artifact import (
    ArtifactCreate,
    ArtifactListResponse,
    ArtifactResponse,
    ArtifactUpdate,
    ArtifactVersionResponse,
)
from mimir.services import artifact_service

router = APIRouter(prefix="/artifacts", tags=["artifacts"])


@router.post("", response_model=ArtifactResponse, status_code=201)
async def create_artifact(
    data: ArtifactCreate,
    x_tenant_id: int = Header(..., alias="X-Tenant-ID"),
) -> ArtifactResponse:
    """Create a new artifact."""
    return await artifact_service.create_artifact(x_tenant_id, data)


@router.get("", response_model=ArtifactListResponse)
async def list_artifacts(
    x_tenant_id: int = Header(..., alias="X-Tenant-ID"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    artifact_type: str | None = Query(None),
    parent_artifact_id: int | None = Query(None),
) -> ArtifactListResponse:
    """List artifacts."""
    return await artifact_service.list_artifacts(
        x_tenant_id, page, page_size, artifact_type, parent_artifact_id
    )


@router.get("/{artifact_id}", response_model=ArtifactResponse)
async def get_artifact(
    artifact_id: int,
    x_tenant_id: int = Header(..., alias="X-Tenant-ID"),
) -> ArtifactResponse:
    """Get artifact by ID."""
    result = await artifact_service.get_artifact(artifact_id, x_tenant_id)
    if not result:
        raise HTTPException(status_code=404, detail="Artifact not found")
    return result


@router.patch("/{artifact_id}", response_model=ArtifactResponse)
async def update_artifact(
    artifact_id: int,
    data: ArtifactUpdate,
    x_tenant_id: int = Header(..., alias="X-Tenant-ID"),
) -> ArtifactResponse:
    """Update an artifact."""
    result = await artifact_service.update_artifact(artifact_id, x_tenant_id, data)
    if not result:
        raise HTTPException(status_code=404, detail="Artifact not found")
    return result


@router.delete("/{artifact_id}", status_code=204)
async def delete_artifact(
    artifact_id: int,
    x_tenant_id: int = Header(..., alias="X-Tenant-ID"),
) -> None:
    """Delete an artifact."""
    deleted = await artifact_service.delete_artifact(artifact_id, x_tenant_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Artifact not found")


@router.get("/{artifact_id}/children", response_model=list[ArtifactResponse])
async def get_artifact_children(
    artifact_id: int,
    x_tenant_id: int = Header(..., alias="X-Tenant-ID"),
) -> list[ArtifactResponse]:
    """Get child artifacts."""
    return await artifact_service.get_children(artifact_id, x_tenant_id)


# Version endpoints
@router.get("/{artifact_id}/versions", response_model=list[ArtifactVersionResponse])
async def get_artifact_versions(
    artifact_id: int,
    x_tenant_id: int = Header(..., alias="X-Tenant-ID"),
) -> list[ArtifactVersionResponse]:
    """Get all versions of an artifact."""
    return await artifact_service.get_versions(artifact_id, x_tenant_id)


@router.get(
    "/{artifact_id}/versions/{version_number}",
    response_model=ArtifactVersionResponse,
)
async def get_artifact_version(
    artifact_id: int,
    version_number: int,
    x_tenant_id: int = Header(..., alias="X-Tenant-ID"),
) -> ArtifactVersionResponse:
    """Get a specific version."""
    result = await artifact_service.get_version(
        artifact_id, version_number, x_tenant_id
    )
    if not result:
        raise HTTPException(status_code=404, detail="Version not found")
    return result


@router.post(
    "/{artifact_id}/versions",
    response_model=ArtifactVersionResponse,
    status_code=201,
)
async def create_artifact_version(
    artifact_id: int,
    x_tenant_id: int = Header(..., alias="X-Tenant-ID"),
    title: str | None = None,
    content: str | None = None,
    change_reason: str | None = None,
    changed_by: str | None = None,
) -> ArtifactVersionResponse:
    """Create a new version."""
    result = await artifact_service.create_version(
        artifact_id, x_tenant_id, title, content, change_reason, changed_by
    )
    if not result:
        raise HTTPException(status_code=404, detail="Artifact not found")
    return result
