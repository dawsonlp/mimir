"""Tenant API endpoints.

Tenants provide multi-tenant data isolation in Mímir. Each tenant represents
a separate context (environment, project, or experiment) with complete data isolation.
Tenant deletion via FK CASCADE removes all associated content.
"""

from fastapi import APIRouter, HTTPException, Query, Response

from mimir.schemas.tenant import (
    TenantCreate,
    TenantListResponse,
    TenantResponse,
    TenantUpdate,
)
from mimir.services import tenant_service

router = APIRouter(prefix="/tenants", tags=["tenants"])


@router.post("", response_model=TenantResponse, status_code=201)
async def create_tenant(data: TenantCreate) -> TenantResponse:
    """Create a new tenant."""
    return await tenant_service.create_tenant(data)


@router.get("", response_model=TenantListResponse)
async def list_tenants(
    active_only: bool = Query(True, description="Only show active tenants"),
) -> TenantListResponse:
    """List all tenants."""
    tenants = await tenant_service.list_tenants(active_only)
    return TenantListResponse(items=tenants, total=len(tenants))


@router.get("/{tenant_id}", response_model=TenantResponse)
async def get_tenant(tenant_id: int) -> TenantResponse:
    """Get tenant by ID."""
    result = await tenant_service.get_tenant(tenant_id)
    if not result:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return result


@router.get("/by-shortname/{shortname}", response_model=TenantResponse)
async def get_tenant_by_shortname(shortname: str) -> TenantResponse:
    """Get tenant by shortname."""
    result = await tenant_service.get_tenant_by_shortname(shortname)
    if not result:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return result


@router.patch("/{tenant_id}", response_model=TenantResponse)
async def update_tenant(tenant_id: int, data: TenantUpdate) -> TenantResponse:
    """Update a tenant."""
    result = await tenant_service.update_tenant(tenant_id, data)
    if not result:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return result


@router.delete("/{tenant_id}", status_code=204)
async def delete_tenant(tenant_id: int) -> Response:
    """Delete a tenant and all associated data.

    This permanently removes the tenant and all artifacts, relations,
    embeddings, and provenance events via FK CASCADE. The tenant's
    AGE graph is also dropped.
    """
    deleted = await tenant_service.delete_tenant(tenant_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return Response(status_code=204)
