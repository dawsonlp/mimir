"""Search schemas for Pydantic validation."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class SearchType(str, Enum):
    """Type of search to perform."""

    SEMANTIC = "semantic"  # Vector similarity search
    FULLTEXT = "fulltext"  # PostgreSQL FTS
    HYBRID = "hybrid"  # Combined semantic + FTS


class SearchRequest(BaseModel):
    """Schema for search request."""

    query: str = Field(..., min_length=1, max_length=10000, description="Search query")
    search_type: SearchType = Field(
        default=SearchType.HYBRID, description="Type of search to perform"
    )
    model: str | None = Field(
        default=None,
        description="Embedding model for semantic search (e.g., 'voyage-3', 'text-embedding-3-small'). Uses configured default if not specified.",
    )
    limit: int = Field(default=20, ge=1, le=100, description="Maximum results to return")
    offset: int = Field(default=0, ge=0, description="Offset for pagination")
    artifact_types: list[str] | None = Field(
        None, description="Filter by artifact types (conversation, document, note)"
    )
    min_similarity: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Minimum similarity threshold for semantic search",
    )
    include_content: bool = Field(
        default=False, description="Include full content in results"
    )


class SemanticSearchRequest(BaseModel):
    """Schema for semantic-only search request."""

    query: str = Field(..., min_length=1, max_length=10000, description="Search query")
    model: str | None = Field(
        default=None,
        description="Embedding model to use. Uses configured default if not specified.",
    )
    limit: int = Field(default=20, ge=1, le=100, description="Maximum results to return")
    offset: int = Field(default=0, ge=0, description="Offset for pagination")
    artifact_types: list[str] | None = Field(
        None, description="Filter by artifact types"
    )
    min_similarity: float = Field(
        default=0.5, ge=0.0, le=1.0, description="Minimum similarity threshold"
    )
    include_content: bool = Field(
        default=False, description="Include full content in results"
    )


class FulltextSearchRequest(BaseModel):
    """Schema for full-text search request."""

    query: str = Field(..., min_length=1, max_length=1000, description="Search query")
    limit: int = Field(default=20, ge=1, le=100, description="Maximum results to return")
    offset: int = Field(default=0, ge=0, description="Offset for pagination")
    artifact_types: list[str] | None = Field(
        None, description="Filter by artifact types"
    )
    search_title: bool = Field(default=True, description="Search in artifact titles")
    search_content: bool = Field(
        default=True, description="Search in artifact content"
    )
    include_content: bool = Field(
        default=False, description="Include full content in results"
    )


class SearchResultItem(BaseModel):
    """Schema for a single search result."""

    artifact_id: int
    artifact_type: str
    title: str | None
    source: str
    score: float = Field(..., description="Relevance score (higher is better)")
    similarity: float | None = Field(
        None, description="Cosine similarity (for semantic search)"
    )
    rank: float | None = Field(None, description="FTS rank (for full-text search)")
    content_snippet: str | None = Field(
        None, description="Snippet of matching content"
    )
    content: str | None = Field(None, description="Full content (if requested)")
    created_at: datetime
    updated_at: datetime
    metadata: dict | None = None


class SearchResponse(BaseModel):
    """Schema for search response."""

    items: list[SearchResultItem]
    total: int = Field(..., description="Total matching results")
    query: str = Field(..., description="Original search query")
    search_type: SearchType
    limit: int
    offset: int


class SimilarArtifactsRequest(BaseModel):
    """Schema for finding similar artifacts."""

    artifact_id: int = Field(..., description="ID of the artifact to find similar to")
    model: str | None = Field(
        default=None,
        description="Embedding model to use. Uses configured default if not specified.",
    )
    limit: int = Field(default=10, ge=1, le=50, description="Maximum results to return")
    min_similarity: float = Field(
        default=0.7, ge=0.0, le=1.0, description="Minimum similarity threshold"
    )
    include_content: bool = Field(
        default=False, description="Include full content in results"
    )
