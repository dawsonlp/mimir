"""Search API endpoints (V2.1).

V2.1 Changes:
- Semantic/hybrid/similar search now require `embedding_type` parameter
- Uses multi-table vector architecture (one vector table per embedding type)

Mímir provides multiple search strategies optimized for different scenarios. 
Understanding when to use each approach is key to building effective RAG applications.

## Choosing a Search Strategy

| Scenario | Recommended Endpoint | Why |
|----------|---------------------|-----|
| User typed a question/query | `/search/fulltext` | Fast, keyword-based, no embedding needed |
| Semantic similarity (find "like this") | `/search/semantic` | Finds conceptually similar content |
| Best of both worlds | `/search/hybrid` | Combines keyword matching with semantic understanding |
| "More like this" exploration | `/search/similar/{id}` | Find related artifacts from a known starting point |

## Relation-Aware Filtering

All search endpoints support filtering by relationship structure. This is powerful for 
graph-constrained retrieval - finding content that is both relevant AND structurally 
connected to a specific artifact.
"""

from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Query

from mimir.schemas.search import SearchResponse
from mimir.services import search_service
from mimir.services.search_service import RelationDirection

router = APIRouter(prefix="/search", tags=["search"])


# ============================================================================
# FULL-TEXT SEARCH
# ============================================================================

@router.get("/fulltext", response_model=SearchResponse)
async def fulltext_search(
    query: str = Query(..., description="Search text - uses PostgreSQL full-text search"),
    x_tenant_id: int = Header(..., alias="X-Tenant-ID"),
    artifact_types: list[str] | None = Query(
        None,
        description="Filter by artifact types (e.g., 'decision', 'summary', 'note')",
    ),
    limit: int = Query(20, ge=1, le=100, description="Maximum results to return"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    related_to: UUID | None = Query(
        None,
        description="Only return artifacts related to this artifact UUID (graph filter)",
    ),
    relation_type: str | None = Query(
        None,
        description="Filter by relation type (e.g., 'derived_from', 'supports'). Requires related_to.",
    ),
    relation_direction: RelationDirection = Query(
        RelationDirection.BOTH,
        description="Which relations to consider: 'incoming', 'outgoing', or 'both'",
    ),
) -> SearchResponse:
    """Full-text search using PostgreSQL FTS - fast keyword-based retrieval.
    
    ## When to Use Full-Text Search
    
    **Best for:**
    - User-typed queries where exact words matter
    - Finding artifacts containing specific technical terms
    - Quick lookups when you don't have embeddings ready
    - Scenarios where speed is critical (no vector computation)
    
    ## No Embedding Required
    
    Unlike semantic/hybrid/similar search, fulltext search does not require
    embeddings or an embedding_type parameter.
    """
    # Fetch more results when filtering, to account for post-filter reduction
    fetch_limit = limit * 3 if related_to else limit
    
    response = await search_service.fulltext_search(
        x_tenant_id, query, artifact_types, fetch_limit, offset
    )
    
    # Apply relation filter post-search (preserves search scoring)
    if related_to:
        related_ids = await search_service.get_related_artifact_ids(
            x_tenant_id, related_to, relation_type, relation_direction
        )
        filtered = search_service._filter_results_by_relation(response.results, related_ids)
        return SearchResponse(
            results=filtered[:limit],
            total=len(filtered),
            query=response.query,
        )
    
    return response


# ============================================================================
# SEMANTIC SEARCH
# ============================================================================

@router.post("/semantic", response_model=SearchResponse)
async def semantic_search(
    query_vector: list[float],
    x_tenant_id: int = Header(..., alias="X-Tenant-ID"),
    embedding_type: str = Query(
        ...,
        description="Embedding type code (e.g., 'nomic-embed-text'). REQUIRED - determines which vector table to search.",
    ),
    artifact_types: list[str] | None = Query(
        None,
        description="Filter by artifact types (e.g., 'decision', 'summary', 'note')",
    ),
    limit: int = Query(20, ge=1, le=100, description="Maximum results to return"),
    similarity_threshold: float = Query(
        0.0, ge=0.0, le=1.0,
        description="Minimum similarity score (0.0-1.0). Higher = more selective.",
    ),
    related_to: UUID | None = Query(
        None,
        description="Only return artifacts related to this artifact UUID (graph filter)",
    ),
    relation_type: str | None = Query(
        None,
        description="Filter by relation type (e.g., 'derived_from', 'supports'). Requires related_to.",
    ),
    relation_direction: RelationDirection = Query(
        RelationDirection.BOTH,
        description="Which relations to consider: 'incoming', 'outgoing', or 'both'",
    ),
) -> SearchResponse:
    """Semantic search using vector similarity - find conceptually related content.
    
    ## V2.1: Embedding Type Required
    
    You must specify `embedding_type` to tell Mímir which vector table to search.
    Each embedding type has its own HNSW-indexed table with fixed dimensions.
    
    **Example:** `?embedding_type=nomic-embed-text`
    
    ## Request Body
    
    Send the query embedding as a JSON array of floats:
    ```json
    [0.023, -0.041, 0.089, ...]  // Dimensions must match embedding_type
    ```
    
    ## Dimension Validation
    
    Your query vector dimensions must match the embedding type's dimensions:
    - `nomic-embed-text`: 768 dimensions
    - `text-embedding-3-small`: 1536 dimensions
    
    If dimensions don't match, you'll get a 400 Bad Request error.
    """
    # Fetch more results when filtering, to account for post-filter reduction
    fetch_limit = limit * 3 if related_to else limit
    
    try:
        response = await search_service.semantic_search(
            tenant_id=x_tenant_id,
            query_vector=query_vector,
            embedding_type=embedding_type,
            artifact_types=artifact_types,
            limit=fetch_limit,
            similarity_threshold=similarity_threshold,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    # Apply relation filter post-search (preserves search scoring)
    if related_to:
        related_ids = await search_service.get_related_artifact_ids(
            x_tenant_id, related_to, relation_type, relation_direction
        )
        filtered = search_service._filter_results_by_relation(response.results, related_ids)
        return SearchResponse(
            results=filtered[:limit],
            total=len(filtered),
            query=response.query,
        )
    
    return response


# ============================================================================
# HYBRID SEARCH
# ============================================================================

@router.post("/hybrid", response_model=SearchResponse)
async def hybrid_search(
    query: str = Query(..., description="Search text for full-text matching"),
    query_vector: list[float] = ...,
    x_tenant_id: int = Header(..., alias="X-Tenant-ID"),
    embedding_type: str = Query(
        ...,
        description="Embedding type code (e.g., 'nomic-embed-text'). REQUIRED - determines which vector table to search.",
    ),
    artifact_types: list[str] | None = Query(
        None,
        description="Filter by artifact types (e.g., 'decision', 'summary', 'note')",
    ),
    limit: int = Query(20, ge=1, le=100, description="Maximum results to return"),
    rrf_k: int = Query(
        60, ge=1,
        description="RRF constant. Higher = less aggressive rank fusion (60 is standard).",
    ),
    semantic_weight: float = Query(
        0.5, ge=0.0, le=1.0,
        description="Balance between semantic (1.0) and fulltext (0.0). Default 0.5 = equal.",
    ),
    related_to: UUID | None = Query(
        None,
        description="Only return artifacts related to this artifact UUID (graph filter)",
    ),
    relation_type: str | None = Query(
        None,
        description="Filter by relation type (e.g., 'derived_from', 'supports'). Requires related_to.",
    ),
    relation_direction: RelationDirection = Query(
        RelationDirection.BOTH,
        description="Which relations to consider: 'incoming', 'outgoing', or 'both'",
    ),
) -> SearchResponse:
    """Hybrid search combining full-text and semantic search with Reciprocal Rank Fusion.
    
    ## V2.1: Embedding Type Required
    
    You must specify `embedding_type` for the semantic search component.
    
    **Example:** `?query=database%20performance&embedding_type=nomic-embed-text`
    
    ## Request Body
    
    Send the query embedding as a JSON array of floats:
    ```json
    [0.023, -0.041, 0.089, ...]
    ```
    
    ## Tuning the Balance
    
    Use `semantic_weight` to control the balance:
    
    | Weight | Behavior | Best For |
    |--------|----------|----------|
    | `0.0` | 100% fulltext | Technical docs, exact term search |
    | `0.5` | Balanced (default) | General purpose, mixed queries |
    | `1.0` | 100% semantic | "Find similar" queries |
    """
    # Fetch more results when filtering, to account for post-filter reduction
    fetch_limit = limit * 3 if related_to else limit
    
    try:
        response = await search_service.hybrid_search(
            tenant_id=x_tenant_id,
            query=query,
            query_vector=query_vector,
            embedding_type=embedding_type,
            artifact_types=artifact_types,
            limit=fetch_limit,
            rrf_k=rrf_k,
            semantic_weight=semantic_weight,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    # Apply relation filter post-search (preserves search scoring)
    if related_to:
        related_ids = await search_service.get_related_artifact_ids(
            x_tenant_id, related_to, relation_type, relation_direction
        )
        filtered = search_service._filter_results_by_relation(response.results, related_ids)
        return SearchResponse(
            results=filtered[:limit],
            total=len(filtered),
            query=response.query,
        )
    
    return response


# ============================================================================
# SIMILARITY SEARCH
# ============================================================================

@router.get("/similar/{artifact_id}", response_model=SearchResponse)
async def similar_artifacts(
    artifact_id: UUID,
    x_tenant_id: int = Header(..., alias="X-Tenant-ID"),
    embedding_type: str = Query(
        ...,
        description="Embedding type code (e.g., 'nomic-embed-text'). REQUIRED - determines which embedding to use.",
    ),
    limit: int = Query(10, ge=1, le=50, description="Maximum results to return"),
    artifact_types: list[str] | None = Query(
        None,
        description="Filter by artifact types (e.g., 'decision', 'summary', 'note')",
    ),
) -> SearchResponse:
    """Find artifacts similar to a given artifact - "more like this" exploration.
    
    ## V2.1: Embedding Type Required
    
    You must specify which embedding type to use for similarity comparison.
    The artifact must have an embedding of that type.
    
    **Example:** `/search/similar/{uuid}?embedding_type=nomic-embed-text`
    
    ## How It Works
    
    1. Looks up the embedding of the specified artifact (for the given embedding_type)
    2. Runs semantic search using that embedding as the query
    3. Returns similar artifacts, excluding the source artifact itself
    
    **Note:** If the artifact doesn't have an embedding of the specified type,
    returns empty results.
    """
    try:
        return await search_service.similar_artifacts(
            tenant_id=x_tenant_id,
            artifact_id=artifact_id,
            embedding_type=embedding_type,
            limit=limit,
            artifact_types=artifact_types,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))