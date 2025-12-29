"""Pydantic schemas for Embedding entity - vector representations for semantic search.

Embeddings enable "find similar" queries by storing vector representations
of artifact content. Uses HNSW index for fast approximate nearest neighbor.

Supported Models:
- OpenAI: text-embedding-3-small (1536d), text-embedding-3-large (3072d)
- Ollama: nomic-embed-text (768d), mxbai-embed-large (1024d)

Chunking:
- For long documents, create multiple embeddings with chunk_index
- chunk_start/chunk_end track character positions within source

Key Points:
- One embedding per (entity, model, chunk_index) combination
- Embeddings are invisible to semantic search without explicit creation
- HNSW index limited to 2000 dimensions

Usage Examples:
    # Generate embedding for an artifact
    POST /embeddings/generate {"entity_type": "artifact", "entity_id": 123}
    
    # Find similar artifacts
    POST /embeddings/similar {"text": "database architecture", "limit": 10}
    
    # Semantic search
    POST /search/semantic {"query": "PostgreSQL optimization", "model": "text-embedding-3-small"}
"""

from datetime import datetime

from pydantic import BaseModel, Field

from mimir.schemas.relation import EntityType


class EmbeddingBase(BaseModel):
    """Base schema for embedding."""

    entity_type: EntityType = Field(..., description="Type of entity being embedded")
    entity_id: int = Field(..., description="ID of the entity")
    model: str = Field(..., description="Model used to generate embedding")
    dimensions: int = Field(..., description="Vector dimensions")
    chunk_index: int | None = Field(None, description="Chunk index if chunked")
    chunk_start: int | None = Field(None, description="Character position start")
    chunk_end: int | None = Field(None, description="Character position end")


class EmbeddingCreate(BaseModel):
    """Schema for creating a new embedding."""

    entity_type: EntityType
    entity_id: int
    model: str = Field(..., min_length=1, max_length=100)
    embedding: list[float] = Field(..., description="Vector values")
    chunk_index: int | None = None
    chunk_start: int | None = None
    chunk_end: int | None = None


class EmbeddingResponse(EmbeddingBase):
    """Schema for embedding response (without vector)."""

    id: int
    tenant_id: int
    created_at: datetime

    model_config = {"from_attributes": True}


class EmbeddingWithVectorResponse(EmbeddingResponse):
    """Schema for embedding response with vector."""

    embedding: list[float]


class EmbeddingListResponse(BaseModel):
    """Schema for listing embeddings."""

    items: list[EmbeddingResponse]
    total: int


class EmbeddingGenerateRequest(BaseModel):
    """Request to generate embeddings for an entity."""

    entity_type: EntityType
    entity_id: int
    model: str | None = Field(None, description="Model to use (default from config)")
    force: bool = Field(False, description="Regenerate even if exists")


class EmbeddingBatchGenerateRequest(BaseModel):
    """Request to generate embeddings for multiple entities."""

    entity_type: EntityType
    entity_ids: list[int]
    model: str | None = None
    force: bool = False
