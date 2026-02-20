"""Artifact API endpoints.

Artifacts are append-only — no update or delete operations.
Tenant-level deletion via FK CASCADE is the only cleanup mechanism.

V2 Changes:
- UUID path parameters (not INT)
- No PATCH/UPDATE endpoint (append-only)
- No version endpoints (each artifact is its own identity)
- 409 Conflict on duplicate UUID
- Batch retrieval via `ids` query parameter
"""

from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Query

from mimir.schemas.artifact import (
    ArtifactCreate,
    ArtifactListResponse,
    ArtifactResponse,
)
from mimir.services import artifact_service

router = APIRouter(prefix="/artifacts", tags=["artifacts"])

MAX_BATCH_IDS = 100


def _parse_ids(ids_param: str | None) -> list[UUID] | None:
    """Parse comma-separated UUIDs from query parameter.
    
    Returns None if no ids provided (pagination mode).
    Raises HTTPException for invalid UUIDs or exceeding max count.
    """
    if not ids_param:
        return None
    
    raw_ids = [s.strip() for s in ids_param.split(",") if s.strip()]
    
    if not raw_ids:
        return None
    
    if len(raw_ids) > MAX_BATCH_IDS:
        raise HTTPException(
            status_code=400,
            detail=f"Maximum {MAX_BATCH_IDS} IDs allowed per request, got {len(raw_ids)}",
        )
    
    parsed: list[UUID] = []
    for raw_id in raw_ids:
        try:
            parsed.append(UUID(raw_id))
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid UUID format: {raw_id}",
            )
    
    return parsed


@router.post("", response_model=ArtifactResponse, status_code=201)
async def create_artifact(
    data: ArtifactCreate,
    x_tenant_id: int = Header(..., alias="X-Tenant-ID"),
) -> ArtifactResponse:
    """Create a new artifact.
    
    If `id` is provided in the request body, uses that UUID.
    If omitted, server generates a UUID.
    Returns 409 Conflict if the provided UUID already exists.
    """
    result = await artifact_service.create_artifact(x_tenant_id, data)
    if result is None:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Artifact with this ID already exists",
                "existing_id": str(data.id),
            },
        )
    return result


@router.get("", response_model=ArtifactListResponse)
async def list_artifacts(
    x_tenant_id: int = Header(..., alias="X-Tenant-ID"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    artifact_type: str | None = Query(None),
    parent_artifact_id: UUID | None = Query(None),
    content_hash: str | None = Query(None),
    ids: str | None = Query(
        None,
        description="Comma-separated UUIDs for batch retrieval (max 100). "
        "When provided, pagination parameters are ignored.",
    ),
) -> ArtifactListResponse:
    """List artifacts with optional filtering or batch retrieval.
    
    **Batch Mode**: When `ids` is provided, retrieves specific artifacts
    by UUID. Returns artifacts in the order of requested IDs.
    Missing IDs are silently omitted.
    
    **Pagination Mode**: When `ids` is not provided, returns paginated
    list with optional filtering by artifact_type, parent_artifact_id,
    or content_hash.
    """
    parsed_ids = _parse_ids(ids)
    return await artifact_service.list_artifacts(
        x_tenant_id, limit, offset, artifact_type, parent_artifact_id, content_hash, parsed_ids
    )


@router.get("/{artifact_id}", response_model=ArtifactResponse)
async def get_artifact(
    artifact_id: UUID,
    x_tenant_id: int = Header(..., alias="X-Tenant-ID"),
) -> ArtifactResponse:
    """Get artifact by UUID."""
    result = await artifact_service.get_artifact(artifact_id, x_tenant_id)
    if not result:
        raise HTTPException(status_code=404, detail="Artifact not found")
    return result


@router.get("/{artifact_id}/children", response_model=list[ArtifactResponse])
async def get_artifact_children(
    artifact_id: UUID,
    x_tenant_id: int = Header(..., alias="X-Tenant-ID"),
) -> list[ArtifactResponse]:
    """Get child artifacts (for positional types like chunks, quotes)."""
    return await artifact_service.get_children(artifact_id, x_tenant_id)


# NOTE: DELETE endpoint removed — artifacts are append-only
# Tenant-level deletion via DELETE /tenants/{id} handles cleanup via FK CASCADE

# NOTE: PATCH/UPDATE endpoint removed - artifacts are append-only
# NOTE: Version endpoints removed - each artifact is its own identity
#       Use supersedes relation for versioning (editorial intent)