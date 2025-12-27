"""Embedding schemas for Pydantic validation."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class EmbeddingModel(str, Enum):
    """Supported embedding models."""

    OPENAI_TEXT_EMBEDDING_3_SMALL = "openai-text-embedding-3-small"
    OPENAI_TEXT_EMBEDDING_3_LARGE = "openai-text-embedding-3-large"
    OPENAI_TEXT_EMBEDDING_ADA_002 = "openai-text-embedding-ada-002"
    SENTENCE_TRANSFORMERS_ALL_MPNET = "sentence-transformers-all-mpnet"
    SENTENCE_TRANSFORMERS_ALL_MINILM = "sentence-transformers-all-minilm"


# Model dimension mappings
EMBEDDING_DIMENSIONS: dict[EmbeddingModel, int] = {
    EmbeddingModel.OPENAI_TEXT_EMBEDDING_3_SMALL: 1536,
    EmbeddingModel.OPENAI_TEXT_EMBEDDING_3_LARGE: 3072,
    EmbeddingModel.OPENAI_TEXT_EMBEDDING_ADA_002: 1536,
    EmbeddingModel.SENTENCE_TRANSFORMERS_ALL_MPNET: 768,
    EmbeddingModel.SENTENCE_TRANSFORMERS_ALL_MINILM: 384,
}


class EmbeddingCreate(BaseModel):
    """Schema for creating an embedding."""

    artifact_id: int = Field(..., description="ID of the artifact to embed")
    artifact_version_id: int | None = Field(
        None, description="Optional specific version ID"
    )
    model: EmbeddingModel = Field(
        default=EmbeddingModel.OPENAI_TEXT_EMBEDDING_3_SMALL,
        description="Embedding model to use",
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
    model: EmbeddingModel = Field(
        default=EmbeddingModel.OPENAI_TEXT_EMBEDDING_3_SMALL,
        description="Embedding model to use",
    )


class EmbeddingBatchResponse(BaseModel):
    """Schema for batch embedding response."""

    created: int = Field(..., description="Number of embeddings created")
    failed: int = Field(..., description="Number of embeddings that failed")
    errors: list[str] = Field(
        default_factory=list, description="Error messages for failures"
    )
