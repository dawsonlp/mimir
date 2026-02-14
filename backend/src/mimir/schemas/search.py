"""Pydantic schemas for search functionality.

V2.4 (Phase 3 Enhancement, 2026-02-13):
- Added SearchStrategy enum for unified endpoint strategy inference
- Added UnifiedSearchRequest schema for POST /search
- Added strategy field to SearchResponse
- Removed SemanticSearchRequest and HybridSearchRequest (endpoints removed)
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


class SearchStrategy(str, Enum):
    """Ranking strategy for the unified search endpoint.

    Inferred from which ranking inputs the consumer provides:
    - query only → FULLTEXT
    - query_vector only → SEMANTIC
    - query + query_vector → HYBRID
    - similar_to only → SIMILAR
    """

    FULLTEXT = "fulltext"
    SEMANTIC = "semantic"
    HYBRID = "hybrid"
    SIMILAR = "similar"


# =============================================================================
# Response Schemas
# =============================================================================


class SearchResult(BaseModel):
    """Schema for a single search result."""

    artifact: ArtifactResponse
    score: float = Field(..., description="Relevance score")
    rank: int | None = Field(None, description="Rank in results")


class UnifiedSearchRequest(BaseModel):
    """Unified search request body for POST /search.

    The ranking strategy is inferred from which ranking inputs are provided:
    - query only → fulltext (PostgreSQL FTS)
    - query_vector only → semantic (cosine similarity, embedding_type required)
    - query + query_vector → hybrid (RRF, embedding_type required)
    - similar_to only → similar (cosine from existing artifact, embedding_type required)

    Ambiguous or reserved combinations return 422:
    - query_vector + similar_to → ambiguous (two competing vector sources)
    - query + similar_to → reserved for future similar+fulltext re-rank
    - all three → ambiguous
    - none → no ranking input
    """

    # === Ranking inputs (at least one required) ===
    query: str | None = Field(
        None,
        min_length=1,
        description="Text query for fulltext or hybrid search",
    )
    query_vector: list[float] | None = Field(
        None,
        description="Pre-computed embedding vector for semantic or hybrid search",
    )
    similar_to: UUID | None = Field(
        None,
        description="Artifact UUID — find artifacts similar to this one",
    )

    # === Vector configuration ===
    embedding_type: str | None = Field(
        None,
        min_length=3,
        max_length=50,
        description="Embedding type code (required for semantic, hybrid, similar)",
    )
    similarity_threshold: float = Field(
        0.0,
        ge=0.0,
        le=1.0,
        description="Minimum similarity score (semantic/similar strategies only)",
    )

    # === Hybrid tuning ===
    rrf_k: int = Field(
        60,
        ge=1,
        description="RRF constant (hybrid strategy only, default 60)",
    )
    semantic_weight: float = Field(
        0.5,
        ge=0.0,
        le=1.0,
        description="Balance: 0.0=fulltext, 1.0=semantic (hybrid strategy only)",
    )

    # === Universal filters ===
    artifact_types: list[str] | None = Field(
        None,
        description="Filter by artifact type names",
    )
    metadata_filters: dict[str, str | list[str]] | None = Field(
        None,
        description="JSONB metadata filtering. AND across keys, OR within array values. "
        'Example: {"language": "python", "tags": ["api", "core"]}',
    )
    scope_artifact_id: UUID | None = Field(
        None,
        description="Restrict to descendants of this artifact (hierarchy scoping)",
    )

    # === Relation filters ===
    related_to: UUID | None = Field(
        None,
        description="Filter by artifacts related to this UUID",
    )
    relation_type: str | None = Field(
        None,
        description="Relation type filter (requires related_to)",
    )
    relation_direction: RelationDirection = Field(
        RelationDirection.BOTH,
        description="Relation direction: incoming, outgoing, or both",
    )

    # === Pagination ===
    limit: int = Field(20, ge=1, le=100, description="Maximum results to return")
    offset: int = Field(
        0,
        ge=0,
        description="Pagination offset. Deep offsets degrade on HNSW indexes.",
    )


class SearchResponse(BaseModel):
    """Schema for search response."""

    results: list[SearchResult]
    total: int
    query: str
    strategy: SearchStrategy | None = Field(
        None,
        description="Ranking strategy used (unified endpoint only)",
    )
