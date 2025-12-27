"""Pydantic schemas for decision API operations."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class DecisionStatus(str, Enum):
    """Status of a decision."""

    active = "active"
    superseded = "superseded"
    tentative = "tentative"


class DecisionSource(str, Enum):
    """Source/origin of a decision."""

    user = "user"
    llm_proposed = "llm_proposed"
    system = "system"


class DecisionBase(BaseModel):
    """Base decision fields."""

    statement: str = Field(..., min_length=1)
    rationale: str | None = None
    artifact_id: int | None = None
    intent_id: int | None = None
    status: DecisionStatus = DecisionStatus.active
    source: DecisionSource = DecisionSource.user
    metadata: dict = Field(default_factory=dict)


class DecisionCreate(BaseModel):
    """Schema for creating a decision."""

    statement: str = Field(..., min_length=1)
    rationale: str | None = None
    artifact_id: int | None = None
    intent_id: int | None = None
    status: DecisionStatus = DecisionStatus.active
    source: DecisionSource = DecisionSource.user
    metadata: dict = Field(default_factory=dict)


class DecisionUpdate(BaseModel):
    """Schema for updating a decision."""

    statement: str | None = Field(None, min_length=1)
    rationale: str | None = None
    status: DecisionStatus | None = None
    metadata: dict | None = None


class DecisionSupersede(BaseModel):
    """Schema for superseding a decision with a new one."""

    new_statement: str = Field(..., min_length=1)
    new_rationale: str | None = None
    metadata: dict = Field(default_factory=dict)


class DecisionResponse(BaseModel):
    """Schema for decision API responses."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int
    artifact_id: int | None
    intent_id: int | None
    statement: str
    rationale: str | None
    status: DecisionStatus
    source: DecisionSource
    superseded_by_id: int | None
    created_at: datetime
    updated_at: datetime
    metadata: dict


class DecisionListResponse(BaseModel):
    """Paginated list of decisions."""

    items: list[DecisionResponse]
    total: int
    page: int
    page_size: int
