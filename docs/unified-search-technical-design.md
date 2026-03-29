# Technical Design: Unified Search Endpoint (`POST /search`)

**Author**: Mimir Architecture Team  
**Date**: 2026-02-13  
**Phase**: 3 (Search Unification)  
**Status**: ✅ Implemented (v3.0.0)  
**Prerequisites**: Phase 1 (Search Infrastructure) ✅, Phase 2 (Deletion Infrastructure) ✅  
**Source**: [Enhancement Request Evaluation §2](archive/enhancement-request-evaluation.md#2-unified-search-endpoint), [Enhancement Roadmap Item #8](archive/enhancement-roadmap-checklist.md)

---

## 1. Problem Statement

Mimir currently exposes four search endpoints:

| Endpoint | Method | Ranking Strategy |
|----------|--------|-----------------|
| `/search/fulltext` | GET | PostgreSQL FTS (`ts_rank`) |
| `/search/semantic` | POST | pgvector cosine similarity |
| `/search/hybrid` | POST | Reciprocal Rank Fusion (FTS + vector) |
| `/search/similar/{id}` | GET | Cosine similarity from existing artifact |

These endpoints share ~80% of their parameters (filters, pagination, relation constraints, hierarchy scoping, metadata filtering) but evolved independently. This creates:

1. **Feature drift risk**: New capabilities must be added to each endpoint separately. Phase 1 required touching all four endpoints for each of pagination, metadata filtering, and hierarchy scoping.
2. **Inconsistent HTTP methods**: Fulltext and similar use GET; semantic and hybrid use POST. This is an artifact of whether the endpoint needs a request body (for vectors), not a meaningful REST distinction.
3. **Client complexity**: Consumers must understand four endpoints with overlapping contracts rather than one endpoint with progressive disclosure.
4. **Combinability ceiling**: Future search modes (e.g., similar + fulltext re-rank) would require yet another endpoint under the current pattern.

---

## 2. Design Approach

### 2.1 Core Principle: Strategy Inference

The unified endpoint accepts a superset of all parameters. The **ranking strategy is inferred from which ranking inputs the consumer provides**. This follows the Elasticsearch `_search` pattern where the query body determines behavior.

**The unified endpoint is a routing/schema change, not a search algorithm change.** It delegates to the same four service functions (`fulltext_search`, `semantic_search`, `hybrid_search`, `similar_artifacts`) that exist today. No changes to `search_service.py`.

### 2.2 Strategy Inference Table

| `query` | `query_vector` | `similar_to` | Inferred Strategy | `embedding_type` Required? |
|---------|---------------|-------------|-------------------|---------------------------|
| ✓ | — | — | **Fulltext** | No |
| — | ✓ | — | **Semantic** | Yes |
| ✓ | ✓ | — | **Hybrid** | Yes |
| — | — | ✓ | **Similar** | Yes |
| ✓ | — | ✓ | **Error 422** (reserved) | — |
| — | ✓ | ✓ | **Error 422** (ambiguous) | — |
| ✓ | ✓ | ✓ | **Error 422** (ambiguous) | — |
| — | — | — | **Error 422** (no input) | — |

### 2.3 Design Decisions

**`similar_to` + `query` returns error (reserved)**: The evaluation document envisions "similar with fulltext re-rank" as a future capability. Rather than shipping an incomplete implementation, this combination returns a 422. When later implemented, consumers who were getting errors will start getting results — a non-breaking change.

**`query_vector` + `similar_to` is always an error**: These are two competing sources for the vector to search against. There is no reasonable interpretation of "use this pre-computed vector AND also look up the vector for this artifact."

**`semantic_weight` silently ignored unless hybrid**: Providing `semantic_weight` or `rrf_k` without both `query` and `query_vector` does not produce an error. These parameters are simply unused when the inferred strategy is not hybrid. This follows the principle of least surprise — a client building a generic search form shouldn't need conditional logic to omit tuning parameters.

**`similarity_threshold` silently ignored for fulltext**: Same rationale. Fulltext search uses `ts_rank`, not cosine similarity; the threshold has no meaning.

**Unified endpoint is POST**: All strategies use POST, even fulltext. This is correct because: (a) the request body can contain vectors (large arrays), (b) POST bodies are not cached by intermediaries, which is appropriate for search, and (c) consistency across all strategies is more valuable than HTTP method purity.

---

## 3. Schema Design

### 3.1 New Enum: `SearchStrategy`

Added to `schemas/search.py`:

```python
class SearchStrategy(str, Enum):
    """Ranking strategy for the unified search endpoint."""
    FULLTEXT = "fulltext"
    SEMANTIC = "semantic"
    HYBRID = "hybrid"
    SIMILAR = "similar"
```

### 3.2 New Schema: `UnifiedSearchRequest`

Added to `schemas/search.py`:

```python
class UnifiedSearchRequest(BaseModel):
    """Unified search request body.

    The ranking strategy is inferred from which ranking inputs are provided:
    - query only → fulltext (PostgreSQL FTS)
    - query_vector only → semantic (cosine similarity, embedding_type required)
    - query + query_vector → hybrid (RRF, embedding_type required)
    - similar_to only → similar (cosine from existing artifact, embedding_type required)
    """

    # === Ranking inputs (at least one required) ===
    query: str | None = Field(None, min_length=1,
        description="Text query for fulltext or hybrid search")
    query_vector: list[float] | None = Field(None,
        description="Pre-computed embedding vector for semantic or hybrid search")
    similar_to: UUID | None = Field(None,
        description="Artifact UUID — find artifacts similar to this one")

    # === Vector configuration ===
    embedding_type: str | None = Field(None, min_length=3, max_length=50,
        description="Embedding type code (required for semantic, hybrid, similar)")
    similarity_threshold: float = Field(0.0, ge=0.0, le=1.0,
        description="Minimum similarity score (semantic/similar strategies only)")

    # === Hybrid tuning ===
    rrf_k: int = Field(60, ge=1,
        description="RRF constant (hybrid strategy only, default 60)")
    semantic_weight: float = Field(0.5, ge=0.0, le=1.0,
        description="Balance: 0.0=fulltext, 1.0=semantic (hybrid strategy only)")

    # === Universal filters ===
    artifact_types: list[str] | None = Field(None,
        description="Filter by artifact type names")
    metadata_filters: dict[str, str | list[str]] | None = Field(None,
        description="JSONB metadata filtering. AND across keys, OR within array values. "
        "Example: {\"language\": \"python\", \"tags\": [\"api\", \"core\"]}")
    scope_artifact_id: UUID | None = Field(None,
        description="Restrict to descendants of this artifact (hierarchy scoping)")

    # === Relation filters ===
    related_to: UUID | None = Field(None,
        description="Filter by artifacts related to this UUID")
    relation_type: str | None = Field(None,
        description="Relation type filter (requires related_to)")
    relation_direction: RelationDirection = Field(RelationDirection.BOTH,
        description="Relation direction: incoming, outgoing, or both")

    # === Pagination ===
    limit: int = Field(20, ge=1, le=100,
        description="Maximum results to return")
    offset: int = Field(0, ge=0,
        description="Pagination offset. Deep offsets degrade on HNSW indexes.")
```

### 3.3 Updated Response: `SearchResponse`

Add optional `strategy` field (backward compatible — existing endpoints don't set it):

```python
class SearchResponse(BaseModel):
    """Schema for search response."""
    results: list[SearchResult]
    total: int
    query: str
    strategy: SearchStrategy | None = Field(None,
        description="Ranking strategy used (unified endpoint only)")
```

---

## 4. Router Design

### 4.1 Strategy Inference Function

This is a **pure function** — no I/O, no database access, directly testable with unit tests.

```python
def _infer_search_strategy(request: UnifiedSearchRequest) -> SearchStrategy:
    """Infer ranking strategy from request parameters.

    Returns the inferred SearchStrategy.
    Raises HTTPException 422 for ambiguous, reserved, or missing ranking inputs.
    Raises HTTPException 422 when embedding_type is required but missing.
    """
    has_query = request.query is not None
    has_vector = request.query_vector is not None
    has_similar = request.similar_to is not None

    # Error: ambiguous — vector + similar conflict
    if has_vector and has_similar:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "AMBIGUOUS_RANKING",
                "detail": "Ambiguous request: cannot combine query_vector with similar_to. "
                "Use query_vector for semantic search, or similar_to for similarity search.",
            },
        )

    # Error: reserved — similar + query (future: re-rank)
    if has_query and has_similar:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "RESERVED_COMBINATION",
                "detail": "Combining similar_to with query is reserved for a future release. "
                "Use similar_to alone for similarity search, or query + query_vector for hybrid search.",
            },
        )

    # Determine strategy
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
                "detail": "No ranking input provided. Supply at least one of: "
                "query (for fulltext), query_vector (for semantic), "
                "query + query_vector (for hybrid), similar_to (for similarity).",
            },
        )

    # Validate embedding_type requirement
    if strategy in (SearchStrategy.SEMANTIC, SearchStrategy.HYBRID, SearchStrategy.SIMILAR):
        if not request.embedding_type:
            param = "query_vector" if has_vector else "similar_to"
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "MISSING_EMBEDDING_TYPE",
                    "detail": f"embedding_type is required for {strategy.value} search "
                    f"(inferred because you provided {param}).",
                },
            )

    return strategy
```

### 4.2 Strategy Execution Functions

Four thin delegation functions that extract parameters from `UnifiedSearchRequest` and call the existing service functions. Example for fulltext:

```python
async def _execute_fulltext(
    request: UnifiedSearchRequest, tenant_id: int
) -> SearchResponse:
    """Delegate to fulltext search service function."""
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
            results=filtered[:request.limit], total=len(filtered), query=response.query
        )

    return response
```

The same pattern applies to `_execute_semantic`, `_execute_hybrid`, and `_execute_similar` — each extracts the relevant subset of parameters and calls the corresponding service function. The relation-filtering post-processing (fetch extra, filter, trim) is replicated from the existing router code.

### 4.3 Unified Endpoint

```python
@router.post("", response_model=SearchResponse)
async def unified_search(
    request: UnifiedSearchRequest,
    x_tenant_id: int = Header(..., alias="X-Tenant-ID"),
) -> SearchResponse:
    """Unified search endpoint — all ranking strategies in one request.

    The ranking strategy is automatically inferred from which parameters
    you provide. See the request schema for the inference rules.
    """
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

    response.strategy = strategy
    return response
```

### 4.4 Deprecation Headers

A FastAPI response callback applied to each existing endpoint:

```python
def _add_deprecation_headers(response: Response):
    """Add RFC 8594 deprecation headers to legacy search endpoints."""
    response.headers["Deprecation"] = "true"
    response.headers["Sunset"] = "Sat, 01 Aug 2026 00:00:00 GMT"
    response.headers["Link"] = '</search>; rel="successor-version"'
```

Applied by wrapping each existing endpoint function to call the callback after execution, or by adding a shared `dependencies` parameter to each route decorator.

---

## 5. Error Message Design

Every error from the unified endpoint explains **what was inferred and why**:

| Scenario | HTTP Status | `code` | Message |
|----------|------------|--------|---------|
| No ranking input | 422 | `NO_RANKING_INPUT` | "No ranking input provided. Supply at least one of: query (for fulltext), query_vector (for semantic), query + query_vector (for hybrid), similar_to (for similarity)." |
| `query_vector` without `embedding_type` | 422 | `MISSING_EMBEDDING_TYPE` | "embedding_type is required for semantic search (inferred because you provided query_vector)." |
| `similar_to` without `embedding_type` | 422 | `MISSING_EMBEDDING_TYPE` | "embedding_type is required for similar search (inferred because you provided similar_to)." |
| `query` + `query_vector` without `embedding_type` | 422 | `MISSING_EMBEDDING_TYPE` | "embedding_type is required for hybrid search (inferred because you provided query_vector)." |
| `query_vector` + `similar_to` | 422 | `AMBIGUOUS_RANKING` | "Ambiguous request: cannot combine query_vector with similar_to. Use query_vector for semantic search, or similar_to for similarity search." |
| `similar_to` + `query` | 422 | `RESERVED_COMBINATION` | "Combining similar_to with query is reserved for a future release. Use similar_to alone for similarity search, or query + query_vector for hybrid search." |
| Invalid `embedding_type` | 400 | (from service) | "Embedding type 'xxx' not found or inactive" |
| Vector dimension mismatch | 400 | (from service) | "Query vector dimensions mismatch: xxx expects N, got M" |

---

## 6. Files Changed

| File | Change Type | Description |
|------|------------|-------------|
| `backend/src/mimir/schemas/search.py` | Modified | Add `SearchStrategy` enum, `UnifiedSearchRequest` schema, `strategy` field on `SearchResponse` |
| `backend/src/mimir/routers/search.py` | Modified | Add `POST /search` endpoint, `_infer_search_strategy()`, four `_execute_*` delegation functions, deprecation headers on legacy endpoints |
| `backend/src/mimir/main.py` | No change | Same `search.router` already registered — the new `POST /search` is on the same router |
| `backend/src/mimir/services/search_service.py` | No change | Unified endpoint delegates to existing service functions |
| `backend/tests/unit/test_unified_search.py` | New | Strategy inference unit tests, schema validation tests |
| `backend/tests/integration/test_unified_search.py` | New | End-to-end tests: each strategy, error cases, filter combinations, deprecation headers |
| `docs/archive/enhancement-roadmap-checklist.md` | Modified | Check off Phase 3 items as completed (archived) |

---

## 7. What This Design Does NOT Do

- **No new search algorithms**: Delegates to the same 4 service functions. No RRF changes, no new vector logic.
- **No database migration**: No schema changes required.
- **No `similar_to` + `query` re-ranking**: Reserved for future. Returns clear 422 today.
- **No server-side embedding generation**: Mimir accepts `query_vector` (pre-computed). This principle is preserved.

> **Update (v3.0.0)**: Legacy endpoints `POST /search/semantic`, `POST /search/hybrid`, and `GET /search/similar/{id}` have been removed. `GET /search/fulltext` remains as a deprecated convenience (sunset 2026-08-01). See `comms/06_v3_migration_guide.md`.

---

## 8. Migration Guide & Deprecation Timeline

See [`comms/06_v3_migration_guide.md`](../comms/06_v3_migration_guide.md) for:
- Before/after examples for all four search strategies
- Deprecation timeline and sunset dates
- New features available in the unified endpoint

---

## 10. Testing Strategy

### 10.1 Unit Tests (`tests/unit/test_unified_search.py`)

Strategy inference is a pure function — test all 8 rows of the inference table plus edge cases:

| Test | Input | Expected |
|------|-------|----------|
| `test_infer_fulltext` | `query="test"` | `FULLTEXT` |
| `test_infer_semantic` | `query_vector=[...]`, `embedding_type="x"` | `SEMANTIC` |
| `test_infer_hybrid` | `query="test"`, `query_vector=[...]`, `embedding_type="x"` | `HYBRID` |
| `test_infer_similar` | `similar_to=UUID`, `embedding_type="x"` | `SIMILAR` |
| `test_error_no_input` | (nothing) | 422 `NO_RANKING_INPUT` |
| `test_error_vector_plus_similar` | `query_vector=[...]`, `similar_to=UUID` | 422 `AMBIGUOUS_RANKING` |
| `test_error_query_plus_similar` | `query="test"`, `similar_to=UUID` | 422 `RESERVED_COMBINATION` |
| `test_error_all_three` | `query`, `query_vector`, `similar_to` | 422 `AMBIGUOUS_RANKING` |
| `test_error_semantic_no_embedding_type` | `query_vector=[...]` | 422 `MISSING_EMBEDDING_TYPE` |
| `test_error_similar_no_embedding_type` | `similar_to=UUID` | 422 `MISSING_EMBEDDING_TYPE` |
| `test_error_hybrid_no_embedding_type` | `query="test"`, `query_vector=[...]` | 422 `MISSING_EMBEDDING_TYPE` |
| `test_schema_validation` | Field constraints: limit, offset, min_length, etc. | Pydantic validation errors |

### 10.2 Integration Tests (`tests/integration/test_unified_search.py`)

Tests against a running Mimir instance with test data:

| Test | Description |
|------|-------------|
| `test_fulltext_via_unified` | `POST /search {"query": "..."}` returns results ranked by FTS |
| `test_semantic_via_unified` | `POST /search {"query_vector": [...], "embedding_type": "..."}` returns results ranked by similarity |
| `test_hybrid_via_unified` | `POST /search {"query": "...", "query_vector": [...], "embedding_type": "..."}` returns RRF-merged results |
| `test_similar_via_unified` | `POST /search {"similar_to": "...", "embedding_type": "..."}` returns similar artifacts |
| `test_metadata_filters_via_unified` | All strategies respect `metadata_filters` |
| `test_scope_via_unified` | All strategies respect `scope_artifact_id` |
| `test_relation_filter_via_unified` | All strategies respect `related_to` filter |
| `test_pagination_via_unified` | `offset` and `limit` work across all strategies |
| `test_response_includes_strategy` | Response `strategy` field matches inferred strategy |
| `test_deprecation_headers_fulltext` | `GET /search/fulltext` returns `Deprecation: true` header |
| `test_deprecation_headers_semantic` | `POST /search/semantic` returns `Deprecation: true` header |
| `test_deprecation_headers_hybrid` | `POST /search/hybrid` returns `Deprecation: true` header |
| `test_deprecation_headers_similar` | `GET /search/similar/{id}` returns `Deprecation: true` header |

---

## Developer's Implementation Checklist

### Schema Layer (`schemas/search.py`)
- [x] Add `SearchStrategy` enum with values: `fulltext`, `semantic`, `hybrid`, `similar`
- [x] Add `UnifiedSearchRequest` Pydantic model with all fields per §3.2
- [x] Add `strategy: SearchStrategy | None` field to `SearchResponse` with `default=None`

### Router Layer (`routers/search.py`)
- [x] Implement `_infer_search_strategy(request) -> SearchStrategy` pure function per §4.1
- [x] Implement `_execute_fulltext(request, tenant_id) -> SearchResponse` delegation function
- [x] Implement `_execute_semantic(request, tenant_id) -> SearchResponse` delegation function
- [x] Implement `_execute_hybrid(request, tenant_id) -> SearchResponse` delegation function
- [x] Implement `_execute_similar(request, tenant_id) -> SearchResponse` delegation function
- [x] Implement `POST /search` endpoint (`unified_search`) per §4.3
- [x] Implement `_add_deprecation_headers()` callback per §4.4
- [x] Apply deprecation headers to `GET /search/fulltext`
- [x] ~~Apply deprecation headers to `POST /search/semantic`~~ — endpoint removed in v3.0.0
- [x] ~~Apply deprecation headers to `POST /search/hybrid`~~ — endpoint removed in v3.0.0
- [x] ~~Apply deprecation headers to `GET /search/similar/{id}`~~ — endpoint removed in v3.0.0
- [x] Update router module docstring to document unified endpoint

### Unit Tests (`tests/unit/test_unified_search.py`)
- [x] Test strategy inference: fulltext (query only)
- [x] Test strategy inference: semantic (query_vector + embedding_type)
- [x] Test strategy inference: hybrid (query + query_vector + embedding_type)
- [x] Test strategy inference: similar (similar_to + embedding_type)
- [x] Test error: no ranking input → 422 NO_RANKING_INPUT
- [x] Test error: query_vector + similar_to → 422 AMBIGUOUS_RANKING
- [x] Test error: query + similar_to → 422 RESERVED_COMBINATION
- [x] Test error: all three ranking inputs → 422 AMBIGUOUS_RANKING
- [x] Test error: semantic without embedding_type → 422 MISSING_EMBEDDING_TYPE
- [x] Test error: similar without embedding_type → 422 MISSING_EMBEDDING_TYPE
- [x] Test error: hybrid without embedding_type → 422 MISSING_EMBEDDING_TYPE
- [x] Test schema validation: UnifiedSearchRequest field constraints

### Integration Tests (`tests/integration/test_unified_search.py`)
- [x] Test fulltext via unified endpoint returns correct results (+ metadata filters, pagination, artifact_types)
- [x] Test validation error cases return structured error responses (no ranking input, ambiguous, reserved, missing embedding_type)
- [x] Test removed endpoints return 404/405 (semantic, hybrid, similar)
- [x] Test deprecation headers on `GET /search/fulltext`
- [x] Test semantic via unified endpoint returns correct results (similarity ordering, threshold, metadata filter, pagination, error cases)
- [x] Test hybrid via unified endpoint returns correct results (RRF merge, semantic_weight, metadata filter, pagination)
- [x] Test similar via unified endpoint returns correct results (ordering, threshold, nonexistent artifact)
- [x] Test all filter combinations work uniformly (metadata_filters, artifact_types across all strategies)
- [x] Test pagination (offset/limit) across all strategies
- [x] Test response includes `strategy` field (+ standard response shape, legacy endpoint has null strategy)

### Documentation
- [x] Update `docs/archive/enhancement-roadmap-checklist.md` with implementation status (archived)
- [x] Update OpenAPI description in `main.py` TAGS_METADATA for search tag
- [x] Bump API version to 3.0.0 (breaking change — legacy endpoints removed)
- [x] Publish consumer migration guide — `comms/06_v3_migration_guide.md`

### Service Layer
- [x] Verify: **no changes to `search_service.py`** — unified endpoint delegates to existing functions

---

## Changelog

| Date | Change | Reason |
|------|--------|--------|
| 2026-02-13 | Initial technical design | Phase 3 implementation planning |
| 2026-02-13 | Implementation complete | All schema, router, unit test, and documentation items done. Integration tests for live embedding strategies deferred (require running embedding providers). |
| 2026-02-13 | v3.0.0 version bump and legacy endpoint removal | Breaking change — removed semantic, hybrid, similar endpoints. Retained fulltext (deprecated). Updated branding to Mímir V3. |
| 2026-02-13 | Integration tests with real embeddings | 36/36 integration tests pass against live API. Covers all 4 strategies, filters, pagination, ordering, error cases. |
