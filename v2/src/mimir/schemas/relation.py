"""Pydantic schemas for Relation entity - knowledge graph edges.

Relations connect artifacts and artifact versions to form a knowledge graph.
They enable lineage tracking, evidence linking, and hierarchical organization.

Relation Types (with inverses):
- references ↔ referenced_by: Citations, links
- supports ↔ supported_by: Evidence backing claims
- contradicts (symmetric): Conflicting information
- derived_from ↔ source_of: Lineage tracking (e.g., decision from conversation)
- supersedes ↔ superseded_by: Versioning of concepts
- parent_of ↔ child_of: Hierarchical grouping
- implements ↔ implemented_by: Requirements to solutions
- resolves ↔ resolved_by: Questions to answers, intents to decisions
- related_to (symmetric): General association

Entity Types:
- artifact: The main knowledge unit
- artifact_version: Immutable snapshot of an artifact

Usage Examples:
    # Decision resolves an intent
    POST /relations {
        "relation_type": "resolves",
        "source_entity_type": "artifact", "source_entity_id": 101,
        "target_entity_type": "artifact", "target_entity_id": 50
    }
    
    # Decision derived from conversation
    POST /relations {
        "relation_type": "derived_from",
        "source_entity_type": "artifact", "source_entity_id": 101,
        "target_entity_type": "artifact", "target_entity_id": 25
    }
    
    # Query all relations for an artifact
    GET /relations/artifact/101
"""

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
