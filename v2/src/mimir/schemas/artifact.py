"""Pydantic schemas for artifact table (V2 unified model)."""

from datetime import datetime

from pydantic import BaseModel, Field


class ArtifactBase(BaseModel):
    """Base schema for artifact."""

    artifact_type: str = Field(..., description="Type from artifact_type vocabulary")
    parent_artifact_id: int | None = Field(None, description="Parent artifact for hierarchy")
    
    # Positional info (for chunks, quotes, highlights)
    start_offset: int | None = Field(None, description="Character position start")
    end_offset: int | None = Field(None, description="Character position end")
    position_metadata: dict | None = Field(None, description="Page, line, paragraph info")
    
    # Content
    title: str | None = Field(None, description="Title or label")
    content: str | None = Field(None, description="Main content")
    
    # Source tracking
    source: str | None = Field(None, description="Origin: import, manual, generated")
    source_system: str | None = Field(None, description="External system: chatgpt, notion")
    external_id: str | None = Field(None, description="ID in source system")
    
    # Extensible
    metadata: dict | None = Field(default_factory=dict, description="Additional metadata")


class ArtifactCreate(BaseModel):
    """Schema for creating a new artifact."""

    artifact_type: str = Field(..., min_length=1, max_length=50)
    parent_artifact_id: int | None = None
    
    # Positional
    start_offset: int | None = None
    end_offset: int | None = None
    position_metadata: dict | None = None
    
    # Content
    title: str | None = None
    content: str | None = None
    
    # Source
    source: str | None = None
    source_system: str | None = None
    external_id: str | None = None
    
    metadata: dict | None = None


class ArtifactUpdate(BaseModel):
    """Schema for updating an artifact."""

    artifact_type: str | None = None
    parent_artifact_id: int | None = None
    start_offset: int | None = None
    end_offset: int | None = None
    position_metadata: dict | None = None
    title: str | None = None
    content: str | None = None
    source: str | None = None
    source_system: str | None = None
    external_id: str | None = None
    metadata: dict | None = None


class ArtifactResponse(ArtifactBase):
    """Schema for artifact response."""

    id: int
    tenant_id: int
    content_hash: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ArtifactListResponse(BaseModel):
    """Schema for listing artifacts."""

    items: list[ArtifactResponse]
    total: int
    page: int = 1
    page_size: int = 50


# Version schemas
class ArtifactVersionBase(BaseModel):
    """Base schema for artifact version."""

    version_number: int
    title: str | None = None
    content: str | None = None
    content_hash: str | None = None
    change_reason: str | None = None
    changed_by: str | None = None
    metadata: dict | None = None


class ArtifactVersionResponse(ArtifactVersionBase):
    """Schema for artifact version response."""

    id: int
    artifact_id: int
    created_at: datetime

    model_config = {"from_attributes": True}


class ArtifactVersionListResponse(BaseModel):
    """Schema for listing artifact versions."""

    items: list[ArtifactVersionResponse]
    total: int
