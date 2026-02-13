"""Search API endpoints (V2.2).

V2.2 Changes (Phase 1 Enhancement):
- All search types support `offset` for pagination
- All search types support `metadata_filters` for JSONB metadata filtering
- All search types support `scope_artifact_id` for hierarchy scoping

V2.1 Changes:
- Semantic/hybrid/similar search now require `embedding_type` parameter
- Uses multi-table vector architecture (one vector table per embedding type)
- All vector search endpoints use proper request schemas with `query_vector` field

Mímir provides multiple search strategies optimized for different scenarios. 
Understanding when to use each approach is key to building effective RAG applications.

## Choosing a Search Strategy

| Scenario | Recommended Endpoint | Why |
|----------|---------------------|-----|
| User typed a question/query | `/search/fulltext` | Fast, keyword-based, no embedding needed |
| Semantic similarity (find "like this") | `/search/semantic` | Finds conceptually similar content |
| Best of both worlds | `/search/hybrid` | Combines keyword matching with semantic understanding |
| "More like this" exploration | `/search/similar/{id}` | Find related artifacts from a known starting point |

## Filtering Capabilities (V2.2)

All search endpoints support these filters (combinable):

| Filter | Description |
|--------|-------------|
| `artifact_types` | Filter by artifact type names |
| `metadata_filters` | JSONB metadata filtering: AND across keys, OR within array values |
| `scope_artifact_id` | Restrict to descendants of a given artifact (hierarchy scoping) |
| `related_to` + `relation_type` + `relation_direction` | Graph-constrained filtering |

## Pagination

All endpoints support `limit` and `offset`. Note: deep offsets degrade performance
on HNSW vector indexes. For large result sets, prefer keyset pagination.
"""

import json
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Query

from mimir.schemas.search import (
    HybridSearchRequest,
    RelationDirection,
    SearchResponse,
    SemanticSearchRequest,
)
from mimir.services import search_service

router = APIRouter(prefix="/search", tags=["search"])


def _parse_metadata_filters(metadata_filters_json: str | None) -> dict[str, str | list[str]] | None:
    """Parse metadata_filters from JSON string query parameter.

    GET endpoints receive metadata_filters as a JSON string since query params
    cannot natively represent dict structures. This helper parses and validates
    the JSON.

    Args:
        metadata_filters_json: JSON string like '{"language": "python", "tags": ["api", "core"]}'

    Returns:
        Parsed dict, or None if input is None/empty

    Raises:
        HTTPException 400 if JSON is malformed or has invalid types
    """
    if not metadata_filters_json:
        return None

    try:
        parsed = json.loads(metadata_filters_json)
    except json.JSONDecodeError as e:
        raise HTTPException(
            status_code=400,
            detail=f"metadata_filters must be valid JSON: {e}",
        )

    if not isinstance(parsed, dict):
        raise HTTPException(
            status_code=400,
            detail="metadata_filters must be a JSON object (dict)",
        )

    # Validate types: values must be str or list[str]
    for key, value in parsed.items():
        if not isinstance(key, str):
            raise HTTPException(
                status_code=400,
                detail=f"metadata_filters keys must be strings, got {type(key).__name__}",
            )
        if isinstance(value, list):
            if not all(isinstance(v, str) for v in value):
                raise HTTPException(
                    status_code=400,
                    detail=f"metadata_filters array values must contain only strings (key: '{key}')",
                )
        elif not isinstance(value, str):
            raise HTTPException(
                status_code=400,
                detail=f"metadata_filters values must be string or list of strings, "
                f"got {type(value).__name__} for key '{key}'",
            )

    return parsed


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
    metadata_filters: str | None = Query(
        None,
        alias="metadata_filters",
        description='JSON object for metadata filtering. AND across keys, OR within arrays. '
        'Example: {"language": "python", "tags": ["api", "core"]}',
    ),
    scope_artifact_id: UUID | None = Query(
        None,
        description="Restrict search to descendants of this artifact (hierarchy scoping)",
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
    parsed_filters = _parse_metadata_filters(metadata_filters)

    # Fetch more results when relation-filtering, to account for post-filter reduction
    fetch_limit = limit * 3 if related_to else limit

    response = await search_service.fulltext_search(
        x_tenant_id,
        query,
        artifact_types,
        fetch_limit,
        offset,
        metadata_filters=parsed_filters,
        scope_artifact_id=scope_artifact_id,
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
    request: SemanticSearchRequest,
    x_tenant_id: int = Header(..., alias="X-Tenant-ID"),
) -> SearchResponse:
    """Semantic search using vector similarity - find conceptually related content.

    ## V2.2: New Parameters

    - `offset`: Pagination offset (default 0). Deep offsets degrade on HNSW.
    - `metadata_filters`: JSONB metadata filtering (AND across keys, OR within arrays).
    - `scope_artifact_id`: Restrict to descendants of a given artifact.

    ## V2.1: Embedding Type Required

    You must specify `embedding_type` to tell Mímir which vector table to search.
    Each embedding type has its own HNSW-indexed table with fixed dimensions.

    ## Request Body

    ```json
    {
      "query_vector": [0.023, -0.041, 0.089, ...],
      "embedding_type": "nomic-embed-text",
      "limit": 20,
      "offset": 0,
      "similarity_threshold": 0.0,
      "metadata_filters": {"language": "python"},
      "scope_artifact_id": "550e8400-e29b-41d4-a716-446655440000",
      "artifact_types": ["document", "analysis"]
    }
    ```
    """
    # Fetch more results when relation-filtering, to account for post-filter reduction
    fetch_limit = request.limit * 3 if request.related_to else request.limit

    try:
        response = await search_service.semantic_search(
            tenant_id=x_tenant_id,
            query_vector=request.query_vector,
            embedding_type=request.embedding_type,
            artifact_types=request.artifact_types,
            limit=fetch_limit,
            offset=request.offset,
            similarity_threshold=request.similarity_threshold,
            metadata_filters=request.metadata_filters,
            scope_artifact_id=request.scope_artifact_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Apply relation filter post-search (preserves search scoring)
    if request.related_to:
        related_ids = await search_service.get_related_artifact_ids(
            x_tenant_id,
            request.related_to,
            request.relation_type,
            request.relation_direction,
        )
        filtered = search_service._filter_results_by_relation(response.results, related_ids)
        return SearchResponse(
            results=filtered[: request.limit],
            total=len(filtered),
            query=response.query,
        )

    return response


# ============================================================================
# HYBRID SEARCH
# ============================================================================


@router.post("/hybrid", response_model=SearchResponse)
async def hybrid_search(
    request: HybridSearchRequest,
    x_tenant_id: int = Header(..., alias="X-Tenant-ID"),
) -> SearchResponse:
    """Hybrid search combining full-text and semantic search with Reciprocal Rank Fusion.

    ## V2.2: New Parameters

    - `offset`: Pagination offset applied after RRF merge (default 0).
    - `metadata_filters`: JSONB metadata filtering (AND across keys, OR within arrays).
    - `scope_artifact_id`: Restrict to descendants of a given artifact.

    ## V2.1: Embedding Type Required

    You must specify `embedding_type` for the semantic search component.

    ## Tuning the Balance

    Use `semantic_weight` to control the balance:

    | Weight | Behavior | Best For |
    |--------|----------|----------|
    | `0.0` | 100% fulltext | Technical docs, exact term search |
    | `0.5` | Balanced (default) | General purpose, mixed queries |
    | `1.0` | 100% semantic | "Find similar" queries |
    """
    # Fetch more results when relation-filtering, to account for post-filter reduction
    fetch_limit = request.limit * 3 if request.related_to else request.limit

    try:
        response = await search_service.hybrid_search(
            tenant_id=x_tenant_id,
            query=request.query,
            query_vector=request.query_vector,
            embedding_type=request.embedding_type,
            artifact_types=request.artifact_types,
            limit=fetch_limit,
            offset=request.offset,
            rrf_k=request.rrf_k,
            semantic_weight=request.semantic_weight,
            metadata_filters=request.metadata_filters,
            scope_artifact_id=request.scope_artifact_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Apply relation filter post-search (preserves search scoring)
    if request.related_to:
        related_ids = await search_service.get_related_artifact_ids(
            x_tenant_id,
            request.related_to,
            request.relation_type,
            request.relation_direction,
        )
        filtered = search_service._filter_results_by_relation(response.results, related_ids)
        return SearchResponse(
            results=filtered[: request.limit],
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
    offset: int = Query(
        0,
        ge=0,
        description="Pagination offset. Note: deep offsets degrade on HNSW indexes.",
    ),
    artifact_types: list[str] | None = Query(
        None,
        description="Filter by artifact types (e.g., 'decision', 'summary', 'note')",
    ),
    metadata_filters: str | None = Query(
        None,
        alias="metadata_filters",
        description='JSON object for metadata filtering. AND across keys, OR within arrays. '
        'Example: {"language": "python", "tags": ["api", "core"]}',
    ),
    scope_artifact_id: UUID | None = Query(
        None,
        description="Restrict search to descendants of this artifact (hierarchy scoping)",
    ),
) -> SearchResponse:
    """Find artifacts similar to a given artifact - "more like this" exploration.

    ## V2.2: New Parameters

    - `offset`: Pagination offset (default 0).
    - `metadata_filters`: JSONB metadata filtering (JSON string query param).
    - `scope_artifact_id`: Restrict to descendants of a given artifact.

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
    parsed_filters = _parse_metadata_filters(metadata_filters)

    try:
        return await search_service.similar_artifacts(
            tenant_id=x_tenant_id,
            artifact_id=artifact_id,
            embedding_type=embedding_type,
            limit=limit,
            offset=offset,
            artifact_types=artifact_types,
            metadata_filters=parsed_filters,
            scope_artifact_id=scope_artifact_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))