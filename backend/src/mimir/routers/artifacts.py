"""Artifact API endpoints (V2.2 with deletion).

V2.2 Changes (Phase 2):
- DELETE /artifacts/{id} endpoint with policy-based dispatch
- Soft-delete for environment tenants, physical-delete for experiment tenants
- 403 Forbidden for audited (project) tenants
- include_deleted query parameter for administrative access

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
    PhysicalDeleteResponse,
    SoftDeleteResponse,
)
from mimir.services import artifact_service, tenant_service

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
    include_deleted: bool = Query(False, description="Include soft-deleted artifacts (admin)"),
) -> ArtifactResponse:
    """Get artifact by UUID.

    By default, soft-deleted artifacts return 404.
    Use `include_deleted=true` for administrative access.
    """
    result = await artifact_service.get_artifact(artifact_id, x_tenant_id, include_deleted)
    if not result:
        raise HTTPException(status_code=404, detail="Artifact not found")
    return result


@router.get("/{artifact_id}/children", response_model=list[ArtifactResponse])
async def get_artifact_children(
    artifact_id: UUID,
    x_tenant_id: int = Header(..., alias="X-Tenant-ID"),
    include_deleted: bool = Query(False, description="Include soft-deleted children (admin)"),
) -> list[ArtifactResponse]:
    """Get child artifacts (for positional types like chunks, quotes).

    By default excludes soft-deleted children.
    """
    return await artifact_service.get_children(artifact_id, x_tenant_id, include_deleted)


@router.delete(
    "/{artifact_id}",
    response_model=SoftDeleteResponse | PhysicalDeleteResponse,
    responses={
        403: {"description": "Deletion not permitted for this tenant type (no_delete policy)"},
        404: {"description": "Artifact not found or already deleted"},
        409: {"description": "Artifact has active children and cascade=false"},
    },
)
async def delete_artifact(
    artifact_id: UUID,
    x_tenant_id: int = Header(..., alias="X-Tenant-ID"),
    cascade: bool = Query(True, description="Cascade delete to all descendants"),
) -> SoftDeleteResponse | PhysicalDeleteResponse:
    """Delete an artifact according to the tenant's deletion policy.

    - **soft_delete** (environment tenants): Sets deleted_at timestamp. Artifact
      remains in database but is excluded from all queries.
    - **physical_delete** (experiment tenants): Permanently removes artifact and
      all associated data (embeddings, relations, provenance).
    - **no_delete** (project tenants): Returns 403 Forbidden.

    When `cascade=true` (default), all descendant artifacts via parent_artifact_id
    are also deleted. When `cascade=false`, returns 409 if the artifact has active children.
    """
    # Look up tenant's deletion policy
    policy = await tenant_service.get_deletion_policy(x_tenant_id)
    if policy is None:
        raise HTTPException(status_code=404, detail="Tenant not found")

    if policy == "no_delete":
        raise HTTPException(
            status_code=403,
            detail="Deletion not permitted: this tenant type enforces append-only (no_delete policy)",
        )

    try:
        if policy == "physical_delete":
            result = await artifact_service.physical_delete_artifact(
                artifact_id, x_tenant_id, cascade
            )
        else:
            # Default to soft_delete
            result = await artifact_service.soft_delete_artifact(
                artifact_id, x_tenant_id, cascade
            )
    except ValueError as e:
        if str(e) == "has_children":
            raise HTTPException(
                status_code=409,
                detail="Artifact has active children. Use cascade=true or delete children first.",
            )
        raise

    if result is None:
        raise HTTPException(status_code=404, detail="Artifact not found or already deleted")

    return result


# NOTE: PATCH/UPDATE endpoint removed - artifacts are append-only
# NOTE: Version endpoints removed - each artifact is its own identity
#       Use supersedes relation for versioning (editorial intent)
