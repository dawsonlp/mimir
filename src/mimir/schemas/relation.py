"""Pydantic schemas for relation API operations."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class EntityType(str, Enum):
    """Types of entities that can participate in relations."""

    artifact = "artifact"
    artifact_version = "artifact_version"
    intent = "intent"
    intent_group = "intent_group"
    decision = "decision"
    span = "span"


class RelationType(str, Enum):
    """Types of relationships between entities."""

    references = "references"
    supports = "supports"
    contradicts = "contradicts"
    derived_from = "derived_from"
    supersedes = "supersedes"
    related_to = "related_to"
    parent_of = "parent_of"
    child_of = "child_of"
    implements = "implements"
    resolves = "resolves"


# ============================================================================
# Relation Schemas
# ============================================================================


class RelationCreate(BaseModel):
    """Schema for creating a relation."""

    source_type: EntityType
    source_id: int
    target_type: EntityType
    target_id: int
    relation_type: RelationType
    description: str | None = None
    confidence: float | None = Field(None, ge=0.0, le=1.0)
    metadata: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def no_self_relation(self) -> "RelationCreate":
        """Validate that source and target are not the same."""
        if self.source_type == self.target_type and self.source_id == self.target_id:
            raise ValueError("Cannot create a relation from an entity to itself")
        return self


class RelationUpdate(BaseModel):
    """Schema for updating a relation."""

    relation_type: RelationType | None = None
    description: str | None = None
    confidence: float | None = Field(None, ge=0.0, le=1.0)
    metadata: dict | None = None


class RelationResponse(BaseModel):
    """Schema for relation API responses."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int
    source_type: EntityType
    source_id: int
    target_type: EntityType
    target_id: int
    relation_type: RelationType
    description: str | None
    confidence: float | None
    created_at: datetime
    updated_at: datetime
    metadata: dict


class RelationListResponse(BaseModel):
    """Paginated list of relations."""

    items: list[RelationResponse]
    total: int
    page: int
    page_size: int
