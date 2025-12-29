"""Pydantic schemas for provenance_event table."""

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
