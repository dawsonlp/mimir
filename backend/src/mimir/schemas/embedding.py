"""Pydantic schemas for Embedding entity.

Embeddings store vector representations for semantic search.

V2 Changes:
- UUID primary keys
- UUID reference to artifact (not INT)
- No artifact_version reference (removed)
- Append-only (no delete schema)

Usage Examples:
    # Create embedding for artifact
    POST /embeddings {"artifact_id": "...", "model": "text-embedding-3-small", 
                      "dimensions": 1536, "embedding": [...]}
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class EmbeddingBase(BaseModel):
    """Base schema for embedding."""

    artifact_id: UUID = Field(..., description="Artifact UUID")
    model: str = Field(..., description="Embedding model name")
    dimensions: int = Field(..., gt=0, description="Vector dimensions")
    metadata: dict | None = Field(default_factory=dict, description="Additional metadata")


class EmbeddingCreate(BaseModel):
    """Schema for creating a new embedding."""

    artifact_id: UUID = Field(..., description="Artifact UUID")
    model: str = Field(..., min_length=1, max_length=100)
    dimensions: int = Field(..., gt=0)
    embedding: list[float] = Field(..., description="Vector values")
    metadata: dict | None = None


# NOTE: No update or delete schemas - embeddings are append-only


class EmbeddingResponse(EmbeddingBase):
    """Schema for embedding response (without vector data)."""

    id: UUID
    tenant_id: int
    created_at: datetime

    model_config = {"from_attributes": True}


class EmbeddingWithVectorResponse(EmbeddingResponse):
    """Schema for embedding response with vector data."""

    embedding: list[float] | None = None


class EmbeddingListResponse(BaseModel):
    """Schema for listing embeddings."""

    items: list[EmbeddingResponse]
    total: int
    limit: int = 50
    offset: int = 0


class EmbeddingProviderInfo(BaseModel):
    """Schema for embedding provider information."""

    name: str
    models: list[str]
    default_dimensions: dict[str, int]


class EmbeddingProvidersResponse(BaseModel):
    """Schema for listing available embedding providers."""

    providers: list[EmbeddingProviderInfo]
