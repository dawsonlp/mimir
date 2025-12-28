"""Pydantic schemas for artifact API operations."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class ArtifactType(str, Enum):
    """Type of artifact."""

    conversation = "conversation"
    document = "document"
    note = "note"


class ArtifactBase(BaseModel):
    """Base artifact fields."""

    artifact_type: ArtifactType
    source: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="General source category (e.g., file, api, import)",
    )
    source_system: str | None = Field(
        default=None,
        max_length=255,
        description="External system identifier (e.g., chatgpt, notion, github) for external_id provenance",
    )
    external_id: str | None = Field(
        default=None,
        description="Original ID in the source_system (e.g., ChatGPT conversation UUID)",
    )
    title: str | None = None
    metadata: dict = Field(default_factory=dict)


class ArtifactCreate(ArtifactBase):
    """Schema for creating an artifact with initial content."""

    content: str = Field(..., min_length=1)


class ArtifactUpdate(BaseModel):
    """Schema for updating artifact metadata (not content - use versions)."""

    title: str | None = None
    metadata: dict | None = None


class ArtifactVersionCreate(BaseModel):
    """Schema for adding a new version to an artifact."""

    content: str = Field(..., min_length=1)
    created_by: str = "system"


class ArtifactVersionResponse(BaseModel):
    """Schema for artifact version API responses."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    artifact_id: int
    version_number: int
    content: str
    content_hash: str
    created_at: datetime
    created_by: str


class ArtifactResponse(ArtifactBase):
    """Schema for artifact API responses (without content)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int
    created_at: datetime
    updated_at: datetime


class ArtifactDetailResponse(ArtifactResponse):
    """Schema for artifact with latest version content."""

    latest_version: ArtifactVersionResponse | None = None


class ArtifactListResponse(BaseModel):
    """Paginated list of artifacts."""

    items: list[ArtifactResponse]
    total: int
    page: int
    page_size: int
