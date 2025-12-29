"""Pydantic schemas for relation_type vocabulary table."""

from datetime import datetime

from pydantic import BaseModel, Field


class RelationTypeBase(BaseModel):
    """Base schema for relation type."""

    code: str = Field(..., description="Unique code for the relation type")
    display_name: str = Field(..., description="Human-readable name")
    description: str | None = Field(None, description="Description of this relation")
    inverse_code: str | None = Field(None, description="Code of the inverse relation")
    is_symmetric: bool = Field(False, description="True if A→B implies B→A")
    is_active: bool = Field(True, description="Whether this type can be used")
    sort_order: int = Field(0, description="Display order in lists")


class RelationTypeCreate(BaseModel):
    """Schema for creating a new relation type."""

    code: str = Field(..., min_length=1, max_length=50, pattern=r"^[a-z][a-z0-9_]*$")
    display_name: str = Field(..., min_length=1, max_length=100)
    description: str | None = None
    inverse_code: str | None = None
    is_symmetric: bool = False
    is_active: bool = True
    sort_order: int = 0


class RelationTypeUpdate(BaseModel):
    """Schema for updating a relation type."""

    display_name: str | None = None
    description: str | None = None
    inverse_code: str | None = None
    is_symmetric: bool | None = None
    is_active: bool | None = None
    sort_order: int | None = None


class RelationTypeResponse(RelationTypeBase):
    """Schema for relation type response."""

    created_at: datetime

    model_config = {"from_attributes": True}


class RelationTypeListResponse(BaseModel):
    """Schema for listing relation types."""

    items: list[RelationTypeResponse]
    total: int
