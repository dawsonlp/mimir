"""Pydantic schemas for span API operations."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SpanType(str, Enum):
    """Type of span marking."""

    quote = "quote"
    highlight = "highlight"
    annotation = "annotation"
    reference = "reference"
    bookmark = "bookmark"


# ============================================================================
# Span Schemas
# ============================================================================


class SpanBase(BaseModel):
    """Base span fields."""

    artifact_id: int
    artifact_version_id: int | None = None
    span_type: SpanType = SpanType.quote
    start_offset: int = Field(..., ge=0)
    end_offset: int = Field(..., ge=0)
    content: str | None = None
    annotation: str | None = None
    metadata: dict = Field(default_factory=dict)

    @field_validator("end_offset")
    @classmethod
    def end_after_start(cls, v: int, info) -> int:
        """Validate that end_offset is >= start_offset."""
        start = info.data.get("start_offset")
        if start is not None and v < start:
            raise ValueError("end_offset must be >= start_offset")
        return v


class SpanCreate(BaseModel):
    """Schema for creating a span."""

    artifact_id: int
    artifact_version_id: int | None = None
    span_type: SpanType = SpanType.quote
    start_offset: int = Field(..., ge=0)
    end_offset: int = Field(..., ge=0)
    content: str | None = None
    annotation: str | None = None
    metadata: dict = Field(default_factory=dict)

    @field_validator("end_offset")
    @classmethod
    def end_after_start(cls, v: int, info) -> int:
        """Validate that end_offset is >= start_offset."""
        start = info.data.get("start_offset")
        if start is not None and v < start:
            raise ValueError("end_offset must be >= start_offset")
        return v


class SpanUpdate(BaseModel):
    """Schema for updating a span."""

    span_type: SpanType | None = None
    start_offset: int | None = Field(None, ge=0)
    end_offset: int | None = Field(None, ge=0)
    content: str | None = None
    annotation: str | None = None
    metadata: dict | None = None


class SpanResponse(BaseModel):
    """Schema for span API responses."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int
    artifact_id: int
    artifact_version_id: int | None
    span_type: SpanType
    start_offset: int
    end_offset: int
    content: str | None
    annotation: str | None
    created_at: datetime
    updated_at: datetime
    metadata: dict


class SpanListResponse(BaseModel):
    """Paginated list of spans."""

    items: list[SpanResponse]
    total: int
    page: int
    page_size: int
