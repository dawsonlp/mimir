"""Pydantic schemas for provenance API operations."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class ProvenanceEntityType(str, Enum):
    """Types of entities that can have provenance tracked."""

    tenant = "tenant"
    artifact = "artifact"
    artifact_version = "artifact_version"
    intent = "intent"
    intent_group = "intent_group"
    decision = "decision"
    span = "span"
    relation = "relation"
    embedding = "embedding"


class ProvenanceAction(str, Enum):
    """Types of actions that can be recorded in provenance."""

    create = "create"
    update = "update"
    delete = "delete"
    supersede = "supersede"
    archive = "archive"
    restore = "restore"


class ProvenanceActorType(str, Enum):
    """Types of actors that can perform actions."""

    user = "user"
    system = "system"
    llm = "llm"
    api_client = "api_client"
    migration = "migration"


# ============================================================================
# Provenance Schemas
# ============================================================================


class ProvenanceEventCreate(BaseModel):
    """Schema for recording a provenance event."""

    entity_type: ProvenanceEntityType
    entity_id: int
    action: ProvenanceAction
    actor_type: ProvenanceActorType
    actor_id: str | None = None
    actor_name: str | None = None
    reason: str | None = None
    changes: dict | None = None
    metadata: dict = Field(default_factory=dict)
    related_entity_type: ProvenanceEntityType | None = None
    related_entity_id: int | None = None
    correlation_id: str | None = None
    request_id: str | None = None


class ProvenanceEventResponse(BaseModel):
    """Schema for provenance event API responses."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int
    entity_type: ProvenanceEntityType
    entity_id: int
    action: ProvenanceAction
    actor_type: ProvenanceActorType
    actor_id: str | None
    actor_name: str | None
    timestamp: datetime
    reason: str | None
    changes: dict | None
    metadata: dict
    related_entity_type: ProvenanceEntityType | None
    related_entity_id: int | None
    correlation_id: str | None
    request_id: str | None
    created_at: datetime


class ProvenanceEventListResponse(BaseModel):
    """Paginated list of provenance events."""

    items: list[ProvenanceEventResponse]
    total: int
    page: int
    page_size: int


class EntityProvenanceResponse(BaseModel):
    """Provenance history for a specific entity."""

    entity_type: ProvenanceEntityType
    entity_id: int
    events: list[ProvenanceEventResponse]
    total: int
