"""Artifact API endpoints.

Artifacts are the primary storage entities in Mímir - canonical documents,
conversations, and notes that form the foundation of the knowledge base.

Entity Relationships:
- Artifacts have Versions (append-only content history)
- Artifacts can have Embeddings for semantic search
- Artifacts can have Spans for precise text references
- Artifacts can be linked via Relations to other entities
- Artifacts can be associated with Intents and Decisions
- All changes to artifacts are tracked in Provenance
"""

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

router = APIRouter(
    prefix="/artifacts",
    tags=["artifacts"],
    responses={404: {"description": "Artifact not found"}},
)


def _get_tenant_id(x_tenant_id: int = Header(..., description="Tenant ID")) -> int:
    """Extract tenant ID from header."""
    return x_tenant_id


@router.post(
    "",
    response_model=ArtifactDetailResponse,
    status_code=201,
    summary="Create artifact",
    description="""
Create a new artifact with initial content version.

**Semantic Intent**: Artifacts are canonical source documents - conversations,
documents, or notes that preserve original content unchanged.

**Relationships Created**:
- Creates initial ArtifactVersion (v1) with content and SHA-256 hash
- Can later add Embeddings for semantic search
- Can later add Spans for text references
""",
)
async def create_artifact(
    data: ArtifactCreate,
    x_tenant_id: int = Header(..., description="Tenant ID for data isolation"),
) -> ArtifactDetailResponse:
    """Create a new artifact with initial content version."""
    return await artifact_service.create_artifact(x_tenant_id, data)


@router.get(
    "",
    response_model=ArtifactListResponse,
    summary="List artifacts",
    description="List all artifacts for the tenant. Filter by type (conversation, document, note).",
)
async def list_artifacts(
    x_tenant_id: int = Header(..., description="Tenant ID for data isolation"),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    artifact_type: str | None = Query(None, description="Filter by type: conversation, document, note"),
) -> ArtifactListResponse:
    """List artifacts for the tenant with pagination."""
    return await artifact_service.list_artifacts(
        x_tenant_id, page, page_size, artifact_type
    )


@router.get(
    "/{artifact_id}",
    response_model=ArtifactDetailResponse,
    summary="Get artifact",
    description="Get artifact metadata and latest version content. Includes content_hash for integrity verification.",
)
async def get_artifact(
    artifact_id: int,
    x_tenant_id: int = Header(..., description="Tenant ID for data isolation"),
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
    summary="Add version",
    description="""
Add a new content version to an artifact.

**Semantic Intent**: Versions are append-only - original content is never modified.
Each version gets its own SHA-256 content_hash for integrity and deduplication.

**Design**: Supports the requirement that canonical content is never destroyed.
""",
)
async def add_version(
    artifact_id: int,
    data: ArtifactVersionCreate,
    x_tenant_id: int = Header(..., description="Tenant ID for data isolation"),
) -> ArtifactVersionResponse:
    """Add a new version to an artifact."""
    result = await artifact_service.add_version(artifact_id, x_tenant_id, data)
    if not result:
        raise HTTPException(status_code=404, detail="Artifact not found")
    return result


@router.get(
    "/{artifact_id}/versions",
    response_model=list[ArtifactVersionResponse],
    summary="List versions",
    description="Get complete version history of an artifact. Versions are ordered newest-first.",
)
async def get_versions(
    artifact_id: int,
    x_tenant_id: int = Header(..., description="Tenant ID for data isolation"),
) -> list[ArtifactVersionResponse]:
    """Get all versions of an artifact."""
    return await artifact_service.get_versions(artifact_id, x_tenant_id)
