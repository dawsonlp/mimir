"""Pydantic schemas for Embedding entity.

Embeddings store vector representations for semantic search.

V2.1 Changes:
- Now uses embedding_type FK instead of free-form model string
- Dimensions validated against embedding_type definition
- Vectors stored in separate mimir_vectors.vec_{type} tables

Usage Examples:
    # First, register an embedding type (creates vector table):
    POST /embedding-types {"code": "nomic-embed-text", "provider": "ollama", "dimensions": 768}

    # Then create embedding:
    POST /embeddings {"artifact_id": "...", "embedding_type": "nomic-embed-text", "embedding": [...]}
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class EmbeddingCreate(BaseModel):
    """Schema for creating a new embedding."""

    artifact_id: UUID = Field(..., description="Artifact UUID")
    embedding_type: str = Field(
        ...,
        min_length=3,
        max_length=50,
        description="Embedding type code (must be registered first)",
    )
    embedding: list[float] = Field(..., description="Vector values")
    metadata: dict | None = None


# NOTE: No update or delete schemas - embeddings are append-only


class EmbeddingResponse(BaseModel):
    """Schema for embedding response (without vector data)."""

    id: UUID
    tenant_id: int
    artifact_id: UUID
    embedding_type: str
    created_at: datetime
    metadata: dict | None = None

    model_config = {"from_attributes": True}


class EmbeddingWithVectorResponse(EmbeddingResponse):
    """Schema for embedding response with vector data."""

    embedding: list[float] | None = None
    dimensions: int | None = None


class EmbeddingListResponse(BaseModel):
    """Schema for listing embeddings."""

    items: list[EmbeddingResponse]
    total: int
    limit: int = 50
    offset: int = 0


class SimilaritySearchRequest(BaseModel):
    """Schema for similarity search request."""

    query_vector: list[float] = Field(..., description="Query embedding vector")
    embedding_type: str = Field(
        ...,
        min_length=3,
        max_length=50,
        description="Embedding type code (determines which vector table to search)",
    )
    limit: int = Field(default=20, ge=1, le=100)
    similarity_threshold: float = Field(default=0.0, ge=0.0, le=1.0)
    artifact_types: list[str] | None = Field(
        default=None, description="Filter by artifact types"
    )


class SimilarityResult(BaseModel):
    """Schema for a single similarity search result."""

    embedding_id: UUID
    artifact_id: UUID
    embedding_type: str
    similarity: float


class SimilaritySearchResponse(BaseModel):
    """Schema for similarity search response."""

    results: list[SimilarityResult]
    total: int
