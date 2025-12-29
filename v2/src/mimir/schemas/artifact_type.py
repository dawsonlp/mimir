"""Pydantic schemas for artifact_type vocabulary table."""

from datetime import datetime

from pydantic import BaseModel, Field


class ArtifactTypeBase(BaseModel):
    """Base schema for artifact type."""

    code: str = Field(..., description="Unique code for the artifact type")
    display_name: str = Field(..., description="Human-readable name")
    description: str | None = Field(None, description="Description of this type")
    category: str | None = Field(None, description="Category: content, positional, derived")
    is_active: bool = Field(True, description="Whether this type can be used for new artifacts")
    sort_order: int = Field(0, description="Display order in lists")


class ArtifactTypeCreate(BaseModel):
    """Schema for creating a new artifact type."""

    code: str = Field(..., min_length=1, max_length=50, pattern=r"^[a-z][a-z0-9_]*$")
    display_name: str = Field(..., min_length=1, max_length=100)
    description: str | None = None
    category: str | None = Field(None, pattern=r"^(content|positional|derived)$")
    is_active: bool = True
    sort_order: int = 0


class ArtifactTypeUpdate(BaseModel):
    """Schema for updating an artifact type."""

    display_name: str | None = None
    description: str | None = None
    category: str | None = None
    is_active: bool | None = None
    sort_order: int | None = None


class ArtifactTypeResponse(ArtifactTypeBase):
    """Schema for artifact type response."""

    created_at: datetime

    model_config = {"from_attributes": True}


class ArtifactTypeListResponse(BaseModel):
    """Schema for listing artifact types."""

    items: list[ArtifactTypeResponse]
    total: int
