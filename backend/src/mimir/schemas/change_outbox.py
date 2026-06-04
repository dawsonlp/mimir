"""Schemas for Mimir change outbox events."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class ChangeActor(BaseModel):
    """Actor context included in a change event."""

    type: str
    id: str | None = None


class ChangeOutboxEvent(BaseModel):
    """Versioned Kafka payload for a retained outbox row."""

    event_id: UUID
    event_version: Literal[1] = 1
    tenant_id: int
    sequence: int
    entity_type: Literal["artifact", "relation", "embedding"]
    entity_id: UUID
    action: Literal["create"] = "create"
    occurred_at: datetime
    provenance_event_id: UUID | None = None
    correlation_id: UUID | None = None
    actor: ChangeActor | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
