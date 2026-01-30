"""Pydantic schemas for Tenant entity.

Tenant provides multi-tenancy isolation. Each tenant has completely isolated data.
All API calls (except tenant CRUD) require X-Tenant-ID header.

Tenant Types:
- environment: Default type for isolated environments
- project: For project-specific data isolation
- experiment: For experimental/temporary data

Usage:
    POST /tenants {"shortname": "acme", "name": "Acme Corp", "tenant_type": "environment"}
    All subsequent calls: curl -H "X-Tenant-ID: 1" ...
"""

from datetime import datetime

from pydantic import BaseModel, Field


class TenantBase(BaseModel):
    """Base schema for tenant."""

    shortname: str = Field(..., description="Short unique identifier")
    name: str = Field(..., description="Display name")
    tenant_type: str = Field("environment", description="Type: environment, project, experiment")
    description: str | None = Field(None, description="Description")
    is_active: bool = Field(True, description="Whether tenant is active")
    metadata: dict | None = Field(default_factory=dict, description="Additional metadata")


class TenantCreate(BaseModel):
    """Schema for creating a new tenant."""

    shortname: str = Field(..., min_length=1, max_length=50, pattern=r"^[a-z][a-z0-9_-]*$")
    name: str = Field(..., min_length=1, max_length=200)
    tenant_type: str = Field("environment", pattern=r"^(environment|project|experiment)$")
    description: str | None = None
    is_active: bool = True
    metadata: dict | None = None


class TenantUpdate(BaseModel):
    """Schema for updating a tenant."""

    name: str | None = None
    tenant_type: str | None = None
    description: str | None = None
    is_active: bool | None = None
    metadata: dict | None = None


class TenantResponse(TenantBase):
    """Schema for tenant response."""

    id: int
    created_at: datetime

    model_config = {"from_attributes": True}


class TenantListResponse(BaseModel):
    """Schema for listing tenants."""

    items: list[TenantResponse]
    total: int
