"""Pydantic schemas for Provenance Event entity.

Provenance events provide audit trail for all entity creates.

V2 Changes:
- UUID primary keys
- UUID entity references
- Simplified - only 'create' action (append-only system)
- No POST endpoint - events are auto-created
- Read-only from API perspective

Entity Types:
- artifact
- relation
- embedding

Actor Types:
- user: Human user
- system: Automated system process
- llm: Language model
- api_client: External API client
- migration: Database migration

Usage Examples:
    # Query provenance for an artifact
    GET /provenance/artifact/{id}
    
    # Query all provenance events
    GET /provenance?entity_type=artifact&actor_type=api_client
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ProvenanceEventBase(BaseModel):
    """Base schema for provenance event."""

    entity_type: str = Field(..., description="Type: artifact, relation, embedding")
    entity_id: UUID = Field(..., description="Entity UUID")
    action: str = Field(default="create", description="Action: create")
    actor_type: str = Field(..., description="Actor type: user, system, llm, api_client, migration")
    actor_id: str | None = Field(None, description="Actor identifier")
    reason: str | None = Field(None, description="Why the action was taken")
    metadata: dict | None = Field(default_factory=dict, description="Additional details")


class ProvenanceEventCreate(BaseModel):
    """Schema for creating a provenance event (internal use only).
    
    Note: Provenance events are auto-created by the system, not via API.
    """

    entity_type: str
    entity_id: UUID
    action: str = "create"
    actor_type: str
    actor_id: str | None = None
    reason: str | None = None
    metadata: dict | None = None


class ProvenanceEventResponse(ProvenanceEventBase):
    """Schema for provenance event response."""

    id: UUID
    tenant_id: int
    created_at: datetime

    model_config = {"from_attributes": True}


class ProvenanceEventListResponse(BaseModel):
    """Schema for listing provenance events."""

    items: list[ProvenanceEventResponse]
    total: int
    limit: int = 50
    offset: int = 0


# NOTE: Enums removed - using TEXT columns for flexibility
# Entity types: artifact, relation, embedding
# Actions: create (only for now - append-only system)
# Actor types: user, system, llm, api_client, migration
