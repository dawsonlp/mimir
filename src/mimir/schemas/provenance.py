"""Pydantic schemas for ProvenanceEvent entity - immutable audit trail.

Provenance events record who did what, when, and why. They are append-only
(never modified or deleted) and enable compliance and debugging.

Actions:
- create: Entity created
- update: Entity modified (before/after states captured)
- delete: Entity removed
- supersede: Entity replaced by newer version
- archive: Entity made inactive
- restore: Entity reactivated

Actor Types:
- user: Human via UI or direct API call
- system: Internal process or scheduled task
- llm: AI/LLM operation (e.g., automated analysis)
- api_client: External API consumer
- migration: Data migration script

Key Points:
- Automatically recorded for CRUD operations
- Can also record custom business events via API
- Query by entity (full history) or by actor (all activity)

Usage Examples:
    # Query history of an artifact
    GET /provenance/entity/artifact/123
    
    # Query all activity by a user
    GET /provenance/actor/user/john@example.com
    
    # Record custom provenance
    POST /provenance {
        "entity_type": "artifact", "entity_id": 123, "action": "update",
        "actor_type": "user", "actor_id": "jane@example.com",
        "reason": "Fixed typo in title"
    }
"""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

from mimir.schemas.relation import EntityType


class ProvenanceAction(str, Enum):
    """Actions that can be recorded in provenance."""

    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    SUPERSEDE = "supersede"
    ARCHIVE = "archive"
    RESTORE = "restore"


class ProvenanceActorType(str, Enum):
    """Types of actors that can perform actions."""

    USER = "user"
    SYSTEM = "system"
    LLM = "llm"
    API_CLIENT = "api_client"
    MIGRATION = "migration"


class ProvenanceEventBase(BaseModel):
    """Base schema for provenance event."""

    entity_type: EntityType = Field(..., description="Type of entity affected")
    entity_id: int = Field(..., description="ID of the entity")
    action: ProvenanceAction = Field(..., description="Action performed")
    actor_type: ProvenanceActorType = Field(..., description="Type of actor")
    actor_id: str | None = Field(None, description="ID of the actor")
    reason: str | None = Field(None, description="Reason for action")
    before_state: dict | None = Field(None, description="State before action")
    after_state: dict | None = Field(None, description="State after action")
    metadata: dict | None = Field(default_factory=dict, description="Additional context")


class ProvenanceEventCreate(BaseModel):
    """Schema for creating a new provenance event."""

    entity_type: EntityType
    entity_id: int
    action: ProvenanceAction
    actor_type: ProvenanceActorType = ProvenanceActorType.SYSTEM
    actor_id: str | None = None
    reason: str | None = None
    before_state: dict | None = None
    after_state: dict | None = None
    metadata: dict | None = None


class ProvenanceEventResponse(ProvenanceEventBase):
    """Schema for provenance event response."""

    id: int
    tenant_id: int
    created_at: datetime

    model_config = {"from_attributes": True}


class ProvenanceEventListResponse(BaseModel):
    """Schema for listing provenance events."""

    items: list[ProvenanceEventResponse]
    total: int


class ProvenanceQueryParams(BaseModel):
    """Query parameters for filtering provenance events."""

    entity_type: EntityType | None = None
    entity_id: int | None = None
    action: ProvenanceAction | None = None
    actor_type: ProvenanceActorType | None = None
    actor_id: str | None = None
    since: datetime | None = None
    until: datetime | None = None
