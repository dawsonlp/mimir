"""Pydantic schemas for search functionality."""

from pydantic import BaseModel, Field

from mimir.schemas.artifact import ArtifactResponse


class SearchQuery(BaseModel):
    """Schema for search queries."""

    query: str = Field(..., min_length=1, description="Search query text")
    artifact_types: list[str] | None = Field(None, description="Filter by artifact types")
    limit: int = Field(20, ge=1, le=100, description="Maximum results")
    offset: int = Field(0, ge=0, description="Pagination offset")


class SemanticSearchQuery(SearchQuery):
    """Schema for semantic search queries."""

    model: str | None = Field(None, description="Embedding model to use")
    similarity_threshold: float = Field(0.0, ge=0.0, le=1.0, description="Minimum similarity")


class FulltextSearchQuery(SearchQuery):
    """Schema for full-text search queries."""

    pass


class HybridSearchQuery(SearchQuery):
    """Schema for hybrid (RRF) search queries."""

    model: str | None = Field(None, description="Embedding model for semantic component")
    rrf_k: int = Field(60, ge=1, le=1000, description="RRF constant (higher = less aggressive)")
    semantic_weight: float = Field(0.5, ge=0.0, le=1.0, description="Weight for semantic scores")


class SearchResult(BaseModel):
    """Schema for a single search result."""

    artifact: ArtifactResponse
    score: float = Field(..., description="Relevance score")
    rank: int | None = Field(None, description="Rank in results")


class SearchResponse(BaseModel):
    """Schema for search response."""

    results: list[SearchResult]
    total: int
    query: str


class SimilaritySearchRequest(BaseModel):
    """Request to find similar artifacts."""

    artifact_id: int = Field(..., description="Source artifact ID")
    limit: int = Field(10, ge=1, le=100, description="Maximum results")
    artifact_types: list[str] | None = Field(None, description="Filter by types")
    exclude_self: bool = Field(True, description="Exclude the source artifact")
