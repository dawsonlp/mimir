"""Pydantic schemas for tenant API operations."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class TenantType(str, Enum):
    """Tenant categorization."""

    environment = "environment"
    project = "project"
    experiment = "experiment"


class TenantBase(BaseModel):
    """Base tenant fields."""

    shortname: str = Field(..., min_length=1, max_length=100, pattern=r"^[a-z0-9_-]+$")
    name: str = Field(..., min_length=1, max_length=255)
    tenant_type: TenantType = TenantType.project
    description: str | None = None
    metadata: dict = Field(default_factory=dict)


class TenantCreate(TenantBase):
    """Schema for creating a tenant."""

    pass


class TenantUpdate(BaseModel):
    """Schema for updating a tenant (all fields optional)."""

    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    is_active: bool | None = None
    metadata: dict | None = None


class TenantResponse(TenantBase):
    """Schema for tenant API responses."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    is_active: bool
    created_at: datetime
