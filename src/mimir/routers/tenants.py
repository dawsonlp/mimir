"""Tenant API endpoints.

Tenants provide multi-tenant data isolation in Mímir. Each tenant represents
a separate context (environment, project, or experiment) with complete data isolation.

Entity Relationships:
- All entities (Artifacts, Intents, Decisions, etc.) belong to exactly one Tenant
- Tenant ID is passed via X-Tenant-ID header on every API call
- Deleting a tenant is restricted if it has dependent data
"""

from fastapi import APIRouter, HTTPException, Query

from mimir.schemas.tenant import TenantCreate, TenantResponse, TenantUpdate
from mimir.services import tenant_service

router = APIRouter(prefix="/tenants", tags=["tenants"])


@router.post("", response_model=TenantResponse, status_code=201)
async def create_tenant(data: TenantCreate) -> TenantResponse:
    """Create a new tenant."""
    return await tenant_service.create_tenant(data)


@router.get("", response_model=list[TenantResponse])
async def list_tenants(
    active_only: bool = Query(True, description="Only show active tenants"),
) -> list[TenantResponse]:
    """List all tenants."""
    return await tenant_service.list_tenants(active_only)


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
