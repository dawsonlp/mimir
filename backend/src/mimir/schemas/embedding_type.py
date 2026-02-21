"""Pydantic schemas for EmbeddingType entity.

EmbeddingType is a vocabulary table that defines embedding models.
Each type creates a corresponding vector table in mimir_vectors schema.

Usage Examples:
    # Register new embedding type (creates vector table)
    POST /embedding-types {"code": "nomic-embed-text", "display_name": "Nomic Embed Text",
                           "provider": "ollama", "dimensions": 768}
"""

import re
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

# Pattern: lowercase letters/numbers/hyphens, 3-50 chars, must start with letter
EMBEDDING_TYPE_CODE_PATTERN = re.compile(r"^[a-z][a-z0-9-]{2,49}$")

VALID_DISTANCE_METRICS = {"cosine", "l2", "inner_product"}


class EmbeddingTypeCreate(BaseModel):
    """Schema for creating a new embedding type."""

    code: str = Field(
        ..., min_length=3, max_length=50, description="Unique code (lowercase, hyphens)"
    )
    display_name: str = Field(..., min_length=1, max_length=100)
    provider: str = Field(
        ..., min_length=1, max_length=50, description="Provider: ollama, openai, voyage"
    )
    dimensions: int = Field(..., gt=0, le=16000, description="Vector dimensions")
    distance_metric: str = Field(
        default="cosine", description="Distance metric: cosine, l2, inner_product"
    )
    max_tokens: int | None = Field(default=None, gt=0, description="Max input tokens")
    description: str | None = None

    @field_validator("code")
    @classmethod
    def validate_code_pattern(cls, v: str) -> str:
        if not EMBEDDING_TYPE_CODE_PATTERN.match(v):
            raise ValueError(
                "Code must be 3-50 characters, lowercase letters/numbers/hyphens, "
                "starting with a letter"
            )
        return v

    @field_validator("distance_metric")
    @classmethod
    def validate_distance_metric(cls, v: str) -> str:
        if v not in VALID_DISTANCE_METRICS:
            raise ValueError(
                f"distance_metric must be one of: {', '.join(VALID_DISTANCE_METRICS)}"
            )
        return v


class EmbeddingTypeResponse(BaseModel):
    """Schema for embedding type response."""

    code: str
    display_name: str
    provider: str
    dimensions: int
    distance_metric: str
    max_tokens: int | None
    description: str | None
    vector_table_name: str
    is_active: bool
    sort_order: int
    created_at: datetime

    model_config = {"from_attributes": True}


class EmbeddingTypeListResponse(BaseModel):
    """Schema for listing embedding types."""

    items: list[EmbeddingTypeResponse]
    total: int
