"""Pydantic schemas for Relation entity.

Relations connect artifacts with typed relationships.

V2 Changes:
- UUID primary keys (client-generated preferred)
- UUID references to artifacts (not INT)
- Simplified - only connects artifacts (no artifact_version)
- Append-only (no update schema)

Relation Types:
- references / referenced_by
- supports / supported_by
- contradicts (symmetric)
- derived_from / source_of
- supersedes / superseded_by (editorial intent, not identity)
- related_to (symmetric)
- parent_of / child_of
- implements / implemented_by
- resolves / resolved_by

Usage Examples:
    # Create relation with server-generated UUID
    POST /relations {"source_id": "...", "target_id": "...", "relation_type": "derived_from"}

    # Create supersedes relation (editorial intent)
    POST /relations {"source_id": "new-artifact", "target_id": "old-artifact",
                     "relation_type": "supersedes", "confidence": 1.0}
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class RelationBase(BaseModel):
    """Base schema for relation."""

    source_id: UUID = Field(..., description="Source artifact UUID")
    target_id: UUID = Field(..., description="Target artifact UUID")
    relation_type: str = Field(..., description="Type from relation_type vocabulary")
    confidence: float | None = Field(
        None, ge=0.0, le=1.0, description="Confidence score 0.0-1.0"
    )
    metadata: dict | None = Field(
        default_factory=dict, description="Additional metadata"
    )


class RelationCreate(BaseModel):
    """Schema for creating a new relation.

    id is optional - if provided, must be a valid UUID (UUIDv7 preferred).
    If omitted, server generates a UUID.
    """

    id: UUID | None = Field(None, description="Optional client-generated UUID")
    source_id: UUID = Field(..., description="Source artifact UUID")
    target_id: UUID = Field(..., description="Target artifact UUID")
    relation_type: str = Field(..., min_length=1, max_length=50)
    confidence: float | None = Field(None, ge=0.0, le=1.0)
    metadata: dict | None = None


# NOTE: RelationUpdate removed - relations are append-only


class RelationResponse(RelationBase):
    """Schema for relation response."""

    id: UUID
    tenant_id: int
    created_at: datetime

    model_config = {"from_attributes": True}


class RelationListResponse(BaseModel):
    """Schema for listing relations."""

    items: list[RelationResponse]
    total: int
    limit: int = 50
    offset: int = 0


# NOTE: EntityType enum removed - relations only connect artifacts
