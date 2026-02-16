"""Search API endpoints (V2.4).

V2.4 Changes (Phase 3 Enhancement):
- Added unified POST /search endpoint with strategy inference
- Removed POST /search/semantic, POST /search/hybrid, GET /search/similar/{id}
- GET /search/fulltext retained with deprecation headers (simple GET convenience)

## Unified Search Endpoint (V2.4)

The `POST /search` endpoint consolidates all four search strategies into a single
request. The ranking strategy is inferred from which parameters you provide:

| Parameters | Strategy |
|-----------|----------|
| `query` only | Fulltext |
| `query_vector` (+ `embedding_type`) | Semantic |
| `query` + `query_vector` (+ `embedding_type`) | Hybrid |
| `similar_to` (+ `embedding_type`) | Similar |

All filters (`artifact_types`, `metadata_filters`, `scope_artifact_id`, `related_to`)
and pagination (`limit`, `offset`) work uniformly across all strategies.

## Legacy Endpoint (Deprecated)

`GET /search/fulltext` is retained as a convenience endpoint for simple keyword
searches that don't require a request body. It returns deprecation headers.
Migrate to `POST /search` with `{"query": "..."}` before the sunset date.

## Filtering Capabilities

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

from fastapi import APIRouter, Header, HTTPException, Query, Response

from mimir.schemas.search import (
    GraphScope,
    RelationDirection,
    SearchResponse,
    SearchStrategy,
    UnifiedSearchRequest,
)
from mimir.schemas.graph import (
    GraphNotFoundError,
    GraphQueryTimeoutError,
    GraphScopeTooLargeError,
)
from mimir.services import graph_engine, search_service

router = APIRouter(prefix="/search", tags=["search"])


# =============================================================================
# Deprecation Headers (Phase 3)
# =============================================================================

DEPRECATION_SUNSET = "Sat, 01 Aug 2026 00:00:00 GMT"


def _add_deprecation_headers(response: Response) -> None:
    """Add RFC 8594 deprecation headers to legacy search endpoints.

    Signals to consumers that this endpoint is deprecated and they should
    migrate to POST /search before the sunset date.
    """
    response.headers["Deprecation"] = "true"
    response.headers["Sunset"] = DEPRECATION_SUNSET
    response.headers["Link"] = '</search>; rel="successor-version"'


# =============================================================================
# Strategy Inference (Phase 3)
# =============================================================================


def _infer_search_strategy(request: UnifiedSearchRequest) -> SearchStrategy:
    """Infer ranking strategy from request parameters.

    This is a pure function — no I/O, directly testable with unit tests.

    Returns the inferred SearchStrategy.

    Raises:
        HTTPException 422 for ambiguous, reserved, or missing ranking inputs.
        HTTPException 422 when embedding_type is required but missing.
    """
    has_query = request.query is not None
    has_vector = request.query_vector is not None
    has_similar = request.similar_to is not None

    # Error: ambiguous — vector + similar conflict (with or without query)
    if has_vector and has_similar:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "AMBIGUOUS_RANKING",
                "detail": (
                    "Ambiguous request: cannot combine query_vector with similar_to. "
                    "Use query_vector for semantic search, or similar_to for similarity search."
                ),
            },
        )

    # Error: reserved — similar + query (future: re-rank)
    if has_query and has_similar:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "RESERVED_COMBINATION",
                "detail": (
                    "Combining similar_to with query is reserved for a future release. "
                    "Use similar_to alone for similarity search, "
                    "or query + query_vector for hybrid search."
                ),
            },
        )

    # Determine strategy from remaining valid combinations
    if has_similar:
        strategy = SearchStrategy.SIMILAR
    elif has_query and has_vector:
        strategy = SearchStrategy.HYBRID
    elif has_vector:
        strategy = SearchStrategy.SEMANTIC
    elif has_query:
        strategy = SearchStrategy.FULLTEXT
    else:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "NO_RANKING_INPUT",
                "detail": (
                    "No ranking input provided. Supply at least one of: "
                    "query (for fulltext), query_vector (for semantic), "
                    "query + query_vector (for hybrid), similar_to (for similarity)."
                ),
            },
        )

    # Validate embedding_type requirement for vector-based strategies
    if strategy in (SearchStrategy.SEMANTIC, SearchStrategy.HYBRID, SearchStrategy.SIMILAR):
        if not request.embedding_type:
            param = "query_vector" if has_vector else "similar_to"
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "MISSING_EMBEDDING_TYPE",
                    "detail": (
                        f"embedding_type is required for {strategy.value} search "
                        f"(inferred because you provided {param})."
                    ),
                },
            )

    return strategy


# =============================================================================
# Unified Endpoint Delegation Functions (Phase 3)
# =============================================================================


async def _execute_fulltext(
    request: UnifiedSearchRequest, tenant_id: int
) -> SearchResponse:
    """Delegate unified request to fulltext search service function."""
    fetch_limit = request.limit * 3 if request.related_to else request.limit

    response = await search_service.fulltext_search(
        tenant_id=tenant_id,
        query=request.query,
        artifact_types=request.artifact_types,
        limit=fetch_limit,
        offset=request.offset,
        metadata_filters=request.metadata_filters,
        scope_artifact_id=request.scope_artifact_id,
    )

    if request.related_to:
        related_ids = await search_service.get_related_artifact_ids(
            tenant_id, request.related_to, request.relation_type, request.relation_direction
        )
        filtered = search_service._filter_results_by_relation(response.results, related_ids)
        return SearchResponse(
            results=filtered[: request.limit],
            total=len(filtered),
            query=response.query,
        )

    return response


async def _execute_semantic(
    request: UnifiedSearchRequest, tenant_id: int
) -> SearchResponse:
    """Delegate unified request to semantic search service function."""
    fetch_limit = request.limit * 3 if request.related_to else request.limit

    response = await search_service.semantic_search(
        tenant_id=tenant_id,
        query_vector=request.query_vector,
        embedding_type=request.embedding_type,
        artifact_types=request.artifact_types,
        limit=fetch_limit,
        offset=request.offset,
        similarity_threshold=request.similarity_threshold,
        metadata_filters=request.metadata_filters,
        scope_artifact_id=request.scope_artifact_id,
    )

    if request.related_to:
        related_ids = await search_service.get_related_artifact_ids(
            tenant_id, request.related_to, request.relation_type, request.relation_direction
        )
        filtered = search_service._filter_results_by_relation(response.results, related_ids)
        return SearchResponse(
            results=filtered[: request.limit],
            total=len(filtered),
            query=response.query,
        )

    return response


async def _execute_hybrid(
    request: UnifiedSearchRequest, tenant_id: int
) -> SearchResponse:
    """Delegate unified request to hybrid search service function."""
    fetch_limit = request.limit * 3 if request.related_to else request.limit

    response = await search_service.hybrid_search(
        tenant_id=tenant_id,
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

    if request.related_to:
        related_ids = await search_service.get_related_artifact_ids(
            tenant_id, request.related_to, request.relation_type, request.relation_direction
        )
        filtered = search_service._filter_results_by_relation(response.results, related_ids)
        return SearchResponse(
            results=filtered[: request.limit],
            total=len(filtered),
            query=response.query,
        )

    return response


async def _execute_similar(
    request: UnifiedSearchRequest, tenant_id: int
) -> SearchResponse:
    """Delegate unified request to similar artifacts service function."""
    return await search_service.similar_artifacts(
        tenant_id=tenant_id,
        artifact_id=request.similar_to,
        embedding_type=request.embedding_type,
        limit=request.limit,
        offset=request.offset,
        artifact_types=request.artifact_types,
        metadata_filters=request.metadata_filters,
        scope_artifact_id=request.scope_artifact_id,
    )


# =============================================================================
# Helper Functions
# =============================================================================


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


# =============================================================================
# Graph Scope Resolution (V4.0)
# =============================================================================


async def _resolve_graph_scope(
    scope: GraphScope,
    tenant_id: int,
) -> set[str] | None:
    """Resolve a GraphScope into a set of artifact ID strings.

    Calls graph_engine.traverse() and returns the set of artifact UUIDs
    (as strings) that fall within the graph scope. Returns None on error
    after raising the appropriate HTTP exception.

    Args:
        scope: The GraphScope configuration.
        tenant_id: Tenant ID for graph isolation.

    Returns:
        Set of artifact UUID strings within the scope.

    Raises:
        HTTPException: On graph engine errors (422, 504, 404).
    """
    try:
        results = await graph_engine.traverse(
            tenant_id=tenant_id,
            start_artifact_id=scope.root_artifact_id,
            max_depth=scope.max_depth,
            relation_types=scope.relation_types,
            direction=scope.direction,
            include_start=True,  # D2: include root artifact in search scope
        )
    except GraphScopeTooLargeError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "GRAPH_SCOPE_TOO_LARGE",
                "detail": str(exc),
                "count": exc.count,
                "limit": exc.limit,
            },
        )
    except GraphQueryTimeoutError as exc:
        raise HTTPException(
            status_code=504,
            detail={
                "code": "GRAPH_QUERY_TIMEOUT",
                "detail": str(exc),
                "timeout_seconds": exc.timeout_seconds,
            },
        )
    except GraphNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "GRAPH_NOT_FOUND",
                "detail": str(exc),
                "graph_name": exc.graph_name,
            },
        )

    return {str(r.artifact_id) for r in results}


# ============================================================================
# UNIFIED SEARCH (V2.4 — Phase 3)
# ============================================================================


@router.post("", response_model=SearchResponse)
async def unified_search(
    request: UnifiedSearchRequest,
    x_tenant_id: int = Header(..., alias="X-Tenant-ID"),
) -> SearchResponse:
    """Unified search endpoint — all ranking strategies in one request.

    ## Strategy Inference

    The ranking strategy is automatically inferred from which parameters you provide:

    | Parameters Provided | Strategy | `embedding_type` Required? |
    |---------------------|----------|---------------------------|
    | `query` only | **Fulltext** | No |
    | `query_vector` only | **Semantic** | Yes |
    | `query` + `query_vector` | **Hybrid** (RRF) | Yes |
    | `similar_to` only | **Similar** | Yes |

    ## Error Cases

    | Parameters | Error |
    |-----------|-------|
    | `query_vector` + `similar_to` | 422: Ambiguous — two competing vector sources |
    | `query` + `similar_to` | 422: Reserved for future similar+fulltext re-rank |
    | None of the above | 422: No ranking input |
    | Vector strategy without `embedding_type` | 422: Missing required parameter |

    ## Universal Filters

    All strategies support `artifact_types`, `metadata_filters`, `scope_artifact_id`,
    `related_to`, and pagination (`limit`/`offset`).

    ## Response

    The response includes a `strategy` field indicating which ranking strategy was used.
    """
    # Handle graph_scope: traverse first, then filter search to traversal set
    graph_artifact_ids: set[str] | None = None
    if request.graph_scope is not None:
        graph_artifact_ids = await _resolve_graph_scope(
            request.graph_scope, x_tenant_id
        )
        if not graph_artifact_ids:
            # Empty traversal → empty search results
            return SearchResponse(
                results=[],
                total=0,
                query=request.query or "",
                strategy=_infer_search_strategy(request),
            )
    elif request.scope_artifact_id is not None:
        # Backward compat: convert scope_artifact_id to graph_scope internally (D2)
        compat_scope = GraphScope(
            root_artifact_id=request.scope_artifact_id,
            max_depth=1,
            direction="both",
        )
        graph_artifact_ids = await _resolve_graph_scope(
            compat_scope, x_tenant_id
        )
        # Clear scope_artifact_id so downstream doesn't also apply CTE scoping
        request = request.model_copy(update={"scope_artifact_id": None})

    strategy = _infer_search_strategy(request)

    try:
        if strategy == SearchStrategy.FULLTEXT:
            response = await _execute_fulltext(request, x_tenant_id)
        elif strategy == SearchStrategy.SEMANTIC:
            response = await _execute_semantic(request, x_tenant_id)
        elif strategy == SearchStrategy.HYBRID:
            response = await _execute_hybrid(request, x_tenant_id)
        elif strategy == SearchStrategy.SIMILAR:
            response = await _execute_similar(request, x_tenant_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Post-filter by graph scope artifact IDs if resolved
    if graph_artifact_ids is not None:
        response.results = [
            r for r in response.results
            if str(r.artifact.id) in graph_artifact_ids
        ]
        response.total = len(response.results)

    response.strategy = strategy
    return response


# ============================================================================
# FULL-TEXT SEARCH (Deprecated — use POST /search)
# ============================================================================


@router.get("/fulltext", response_model=SearchResponse, deprecated=True)
async def fulltext_search(
    response: Response,
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

    **⚠️ Deprecated**: Use `POST /search` with `{"query": "..."}` instead.
    This endpoint is retained as a GET convenience for simple keyword searches.

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
    _add_deprecation_headers(response)

    parsed_filters = _parse_metadata_filters(metadata_filters)

    # Fetch more results when relation-filtering, to account for post-filter reduction
    fetch_limit = limit * 3 if related_to else limit

    search_response = await search_service.fulltext_search(
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
        filtered = search_service._filter_results_by_relation(search_response.results, related_ids)
        return SearchResponse(
            results=filtered[:limit],
            total=len(filtered),
            query=search_response.query,
        )

    return search_response