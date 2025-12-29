"""Pydantic schemas for relation table (V2 unified model)."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class EntityType(str, Enum):
    """Entity types that can participate in relations."""

    ARTIFACT = "artifact"
    ARTIFACT_VERSION = "artifact_version"


class RelationBase(BaseModel):
    """Base schema for relation."""

    relation_type: str = Field(..., description="Type from relation_type vocabulary")
    source_entity_type: EntityType = Field(..., description="Source entity type")
    source_entity_id: int = Field(..., description="Source entity ID")
    target_entity_type: EntityType = Field(..., description="Target entity type")
    target_entity_id: int = Field(..., description="Target entity ID")
    metadata: dict | None = Field(default_factory=dict, description="Additional metadata")


class RelationCreate(BaseModel):
    """Schema for creating a new relation."""

    relation_type: str = Field(..., min_length=1, max_length=50)
    source_entity_type: EntityType
    source_entity_id: int
    target_entity_type: EntityType
    target_entity_id: int
    metadata: dict | None = None


class RelationUpdate(BaseModel):
    """Schema for updating a relation."""

    relation_type: str | None = None
    metadata: dict | None = None


class RelationResponse(RelationBase):
    """Schema for relation response."""

    id: int
    tenant_id: int
    created_at: datetime

    model_config = {"from_attributes": True}


class RelationListResponse(BaseModel):
    """Schema for listing relations."""

    items: list[RelationResponse]
    total: int


class RelationQueryParams(BaseModel):
    """Query parameters for filtering relations."""

    source_entity_type: EntityType | None = None
    source_entity_id: int | None = None
    target_entity_type: EntityType | None = None
    target_entity_id: int | None = None
    relation_type: str | None = None
