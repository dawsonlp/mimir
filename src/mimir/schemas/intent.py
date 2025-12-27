"""Pydantic schemas for intent and intent group API operations."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class IntentStatus(str, Enum):
    """Status of an intent."""

    active = "active"
    resolved = "resolved"
    parked = "parked"
    abandoned = "abandoned"


class IntentSource(str, Enum):
    """Source/origin of an intent."""

    user = "user"
    llm_proposed = "llm_proposed"
    system = "system"


# ============================================================================
# Intent Group Schemas
# ============================================================================


class IntentGroupBase(BaseModel):
    """Base intent group fields."""

    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    metadata: dict = Field(default_factory=dict)


class IntentGroupCreate(IntentGroupBase):
    """Schema for creating an intent group."""

    pass


class IntentGroupUpdate(BaseModel):
    """Schema for updating an intent group."""

    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    metadata: dict | None = None


class IntentGroupResponse(IntentGroupBase):
    """Schema for intent group API responses."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int
    created_at: datetime
    updated_at: datetime


class IntentGroupListResponse(BaseModel):
    """Paginated list of intent groups."""

    items: list[IntentGroupResponse]
    total: int
    page: int
    page_size: int


# ============================================================================
# Intent Schemas
# ============================================================================


class IntentBase(BaseModel):
    """Base intent fields."""

    title: str = Field(..., min_length=1, max_length=500)
    description: str | None = None
    intent_group_id: int | None = None
    artifact_id: int | None = None
    status: IntentStatus = IntentStatus.active
    source: IntentSource = IntentSource.user
    metadata: dict = Field(default_factory=dict)


class IntentCreate(BaseModel):
    """Schema for creating an intent."""

    title: str = Field(..., min_length=1, max_length=500)
    description: str | None = None
    intent_group_id: int | None = None
    artifact_id: int | None = None
    source: IntentSource = IntentSource.user
    metadata: dict = Field(default_factory=dict)


class IntentUpdate(BaseModel):
    """Schema for updating an intent."""

    title: str | None = Field(None, min_length=1, max_length=500)
    description: str | None = None
    intent_group_id: int | None = None
    status: IntentStatus | None = None
    metadata: dict | None = None


class IntentResponse(BaseModel):
    """Schema for intent API responses."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int
    intent_group_id: int | None
    artifact_id: int | None
    title: str
    description: str | None
    status: IntentStatus
    source: IntentSource
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None
    metadata: dict


class IntentListResponse(BaseModel):
    """Paginated list of intents."""

    items: list[IntentResponse]
    total: int
    page: int
    page_size: int
