"""Embedding schemas for Pydantic validation."""

from datetime import datetime

from pydantic import BaseModel, Field


# Maximum dimensions supported by database (pgvector HNSW index limit is 2000)
MAX_EMBEDDING_DIMENSIONS = 1536


class EmbeddingModelResponse(BaseModel):
    """Schema for embedding model information."""

    model_id: str = Field(..., description="Unique model identifier")
    provider: str = Field(..., description="Provider name (e.g., 'voyage', 'openai')")
    display_name: str = Field(..., description="Human-readable name")
    dimensions: int = Field(..., description="Output embedding dimensions")
    max_tokens: int = Field(..., description="Maximum input tokens")
    description: str = Field(default="", description="Model description")


class EmbeddingProvidersResponse(BaseModel):
    """Schema for listing available embedding providers and models."""

    providers: list[str] = Field(..., description="List of configured provider names")
    models: list[EmbeddingModelResponse] = Field(
        ..., description="All available models from configured providers"
    )
    default_model: str | None = Field(
        None, description="Default model ID (if any provider is configured)"
    )


class EmbeddingCreate(BaseModel):
    """Schema for creating an embedding."""

    artifact_id: int = Field(..., description="ID of the artifact to embed")
    artifact_version_id: int | None = Field(
        None, description="Optional specific version ID"
    )
    model: str | None = Field(
        default=None,
        description="Embedding model to use (defaults to configured default)",
    )
    text: str | None = Field(
        None,
        description="Optional custom text to embed (defaults to artifact content)",
    )
    chunk_index: int = Field(
        default=0, ge=0, description="Chunk index for chunked documents"
    )


class EmbeddingResponse(BaseModel):
    """Schema for embedding response."""

    id: int
    tenant_id: int
    artifact_id: int
    artifact_version_id: int | None
    model: str
    dimensions: int
    chunk_index: int
    chunk_text: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class EmbeddingListResponse(BaseModel):
    """Schema for paginated embedding list response."""

    items: list[EmbeddingResponse]
    total: int
    page: int
    page_size: int


class EmbeddingBatchCreate(BaseModel):
    """Schema for batch embedding creation."""

    artifact_ids: list[int] = Field(
        ..., min_length=1, max_length=100, description="List of artifact IDs to embed"
    )
    model: str | None = Field(
        default=None,
        description="Embedding model to use (defaults to configured default)",
    )


class EmbeddingBatchResponse(BaseModel):
    """Schema for batch embedding response."""

    created: int = Field(..., description="Number of embeddings created")
    failed: int = Field(..., description="Number of embeddings that failed")
    errors: list[str] = Field(
        default_factory=list, description="Error messages for failures"
    )
