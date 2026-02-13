"""Pydantic schemas for search functionality.

Phase 1 Enhancement (2026-02-13):
- Added offset to SemanticSearchRequest, HybridSearchRequest (pagination)
- Added metadata_filters to all search request schemas (JSONB filtering)
- Added scope_artifact_id to all search request schemas (hierarchy scoping)
"""

from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field

from mimir.schemas.artifact import ArtifactResponse


class RelationDirection(str, Enum):
    """Direction for relation-based filtering."""

    INCOMING = "incoming"
    OUTGOING = "outgoing"
    BOTH = "both"


# =============================================================================
# Request Schemas
# =============================================================================


class SemanticSearchRequest(BaseModel):
    """Request body for semantic search.

    Wraps query_vector in a proper schema for consistent API structure.
    """

    query_vector: list[float] = Field(..., description="Query embedding vector")
    embedding_type: str = Field(
        ...,
        min_length=3,
        max_length=50,
        description="Embedding type code (e.g., 'nomic-embed-text')",
    )
    artifact_types: list[str] | None = Field(
        None, description="Filter by artifact types"
    )
    limit: int = Field(20, ge=1, le=100, description="Maximum results to return")
    offset: int = Field(
        0,
        ge=0,
        description="Pagination offset. Note: deep offsets degrade on HNSW indexes; "
        "prefer keyset pagination for large result sets.",
    )
    similarity_threshold: float = Field(
        0.0, ge=0.0, le=1.0, description="Minimum similarity score (0.0-1.0)"
    )
    metadata_filters: dict[str, str | list[str]] | None = Field(
        None,
        description="Filter by artifact metadata. AND across keys, OR within array values. "
        "Example: {\"language\": \"python\", \"tags\": [\"api\", \"core\"]} matches artifacts "
        "where language='python' AND tags is 'api' OR 'core'. "
        "No negation, range queries, or nested metadata supported. "
        "Object wrapper (e.g., {\"not\": \"value\"}) reserved for future negation.",
    )
    scope_artifact_id: UUID | None = Field(
        None,
        description="Restrict search to descendants of this artifact (hierarchy scoping). "
        "Uses parent_artifact_id tree. The scope anchor itself is included in results.",
    )
    related_to: UUID | None = Field(
        None, description="Filter by artifacts related to this UUID"
    )
    relation_type: str | None = Field(
        None, description="Filter by relation type (requires related_to)"
    )
    relation_direction: RelationDirection = Field(
        RelationDirection.BOTH, description="Relation direction filter"
    )


class HybridSearchRequest(BaseModel):
    """Request body for hybrid search (fulltext + semantic with RRF).

    Combines text query and query vector in a proper schema.
    """

    query: str = Field(..., min_length=1, description="Search text for fulltext matching")
    query_vector: list[float] = Field(..., description="Query embedding vector")
    embedding_type: str = Field(
        ...,
        min_length=3,
        max_length=50,
        description="Embedding type code (e.g., 'nomic-embed-text')",
    )
    artifact_types: list[str] | None = Field(
        None, description="Filter by artifact types"
    )
    limit: int = Field(20, ge=1, le=100, description="Maximum results to return")
    offset: int = Field(
        0,
        ge=0,
        description="Pagination offset applied after RRF merge. "
        "Note: deep offsets degrade on HNSW indexes; "
        "prefer keyset pagination for large result sets.",
    )
    rrf_k: int = Field(60, ge=1, description="RRF constant (60 is standard)")
    semantic_weight: float = Field(
        0.5, ge=0.0, le=1.0, description="Balance: 0.0=fulltext, 1.0=semantic"
    )
    metadata_filters: dict[str, str | list[str]] | None = Field(
        None,
        description="Filter by artifact metadata. AND across keys, OR within array values. "
        "Example: {\"language\": \"python\", \"tags\": [\"api\", \"core\"]} matches artifacts "
        "where language='python' AND tags is 'api' OR 'core'. "
        "No negation, range queries, or nested metadata supported. "
        "Object wrapper (e.g., {\"not\": \"value\"}) reserved for future negation.",
    )
    scope_artifact_id: UUID | None = Field(
        None,
        description="Restrict search to descendants of this artifact (hierarchy scoping). "
        "Uses parent_artifact_id tree. The scope anchor itself is included in results.",
    )
    related_to: UUID | None = Field(
        None, description="Filter by artifacts related to this UUID"
    )
    relation_type: str | None = Field(
        None, description="Filter by relation type (requires related_to)"
    )
    relation_direction: RelationDirection = Field(
        RelationDirection.BOTH, description="Relation direction filter"
    )


# =============================================================================
# Response Schemas
# =============================================================================


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