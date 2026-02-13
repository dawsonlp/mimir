# Phase 1: Search Infrastructure — Implementation Complete

**Date**: 2026-02-13  
**Status**: ✅ Implemented, tested, verified on clean rebuild  
**API Version**: V2.2  
**Breaking Changes**: None — all new parameters have safe defaults

---

## Environment Verification

Rebuilt from scratch (`docker compose down -v` → deleted volumes → `docker compose up -d --build`):
- **66 unit tests**: all passing
- **7 integration performance tests**: all passing (fresh database, no prior state)
- **Recursive CTE performance**: median 1.11ms, p95 1.30ms, execution 2.5ms for 201-artifact tree

---

## What Changed

### 1. Pagination on All Search Types

All four search endpoints now support `offset` (default 0, backward-compatible):

| Endpoint | Parameter Location | Notes |
|----------|-------------------|-------|
| `GET /search/fulltext` | Query param `offset` | Already existed — no change |
| `POST /search/semantic` | Body field `offset` | **New** |
| `POST /search/hybrid` | Body field `offset` | **New** — applied after RRF merge |
| `GET /search/similar/{id}` | Query param `offset` | **New** |

**Implementation notes:**
- Fulltext: SQL `OFFSET` (server-side, most efficient)
- Semantic: In-memory slice after scoring/threshold (HNSW doesn't support native offset)
- Hybrid: In-memory slice after RRF score calculation (offset applies to merged ranked list)
- Similar: Delegates to semantic with self-exclusion, then slices

**Performance documentation**: Field descriptions warn that deep offsets degrade on HNSW indexes and recommend keyset pagination for large result sets.

### 2. Metadata Filtering on Search

All four search endpoints now support `metadata_filters`:

| Endpoint | Parameter Location | Format |
|----------|-------------------|--------|
| `GET /search/fulltext` | Query param (JSON string) | `?metadata_filters={"language":"python"}` |
| `POST /search/semantic` | Body field (dict) | `{"metadata_filters": {"language": "python"}}` |
| `POST /search/hybrid` | Body field (dict) | `{"metadata_filters": {"tags": ["api", "core"]}}` |
| `GET /search/similar/{id}` | Query param (JSON string) | `?metadata_filters={"language":"python"}` |

**Semantics:**
- **AND across keys**: `{"language": "python", "framework": "fastapi"}` → must match both
- **OR within arrays**: `{"tags": ["api", "core"]}` → matches if tag is "api" OR "core"
- **Scalar values**: exact match via JSONB containment (`@>`)

**Implementation:**
- Uses parameterized `metadata @> %s::jsonb` containment operator — GIN index compatible
- No string interpolation of keys or values (SQL injection safe)
- GET endpoints receive JSON string, validated with type checking (returns 400 on malformed input)
- Empty filters = no-op (backward-compatible)

**Documented limitations:**
- No negation (reserved: object wrapper `{"not": "value"}` for future extension)
- No range queries
- No nested metadata matching

### 3. Parent-Child Hierarchy Scoping

All four search endpoints now support `scope_artifact_id`:

| Endpoint | Parameter Location |
|----------|-------------------|
| `GET /search/fulltext` | Query param `scope_artifact_id` (UUID) |
| `POST /search/semantic` | Body field `scope_artifact_id` (UUID) |
| `POST /search/hybrid` | Body field `scope_artifact_id` (UUID) |
| `GET /search/similar/{id}` | Query param `scope_artifact_id` (UUID) |

**Behavior:**
- Restricts search results to descendants of the specified artifact (inclusive — the anchor itself is included)
- Uses recursive CTE on `parent_artifact_id` column
- Nonexistent scope anchor → empty results (not an error)
- `tenant_id` enforced at every recursion level (multi-tenant safety)

**Performance (verified on clean database):**
- 201-artifact tree (1 project → 10 files → 19 chunks each): **median 1.11ms, execution 2.5ms**
- Uses index scans (`idx_artifact_created`), memory-based CTE storage (24kB), 100% buffer hits
- Single file scope (20 descendants): 0.50ms
- Leaf chunk scope (1 descendant): 0.34ms

**Deferred:**
- `deleted_at IS NULL` filter in CTE — the column doesn't exist yet; will be added trivially in Phase 2 migration

---

## Files Changed

| File | Change Type | Summary |
|------|------------|---------|
| `backend/src/mimir/schemas/search.py` | Modified | Added `offset`, `metadata_filters`, `scope_artifact_id` to `SemanticSearchRequest` and `HybridSearchRequest` |
| `backend/src/mimir/services/search_service.py` | Modified | Added `_build_metadata_filter()`, `_resolve_scope_descendants()`, `_build_scope_filter()`. Updated all 4 search functions with new parameters. Version bumped to V2.2. |
| `backend/src/mimir/routers/search.py` | Modified | Added `_parse_metadata_filters()` JSON parser for GET endpoints. Added `offset`, `metadata_filters`, `scope_artifact_id` query params to fulltext and similar endpoints. Passes new body fields from semantic and hybrid. Version bumped to V2.2. |
| `backend/tests/unit/test_search_phase1.py` | **New** | 43 unit tests covering all three features |
| `backend/tests/integration/test_hierarchy_performance.py` | **New** | 7 integration performance tests for recursive CTE |
| `docs/enhancement-roadmap-checklist.md` | Modified | Phase 1 items marked complete |

---

## Test Summary

### Unit Tests (43 new + 23 existing = 66 total)

| Test Class | Count | Feature |
|------------|-------|---------|
| `TestPaginationSchemas` | 6 | Offset default/custom/negative validation |
| `TestPaginationSlicing` | 5 | offset=0, skip-N, beyond-total, at-total, partial-page |
| `TestBuildMetadataFilter` | 9 | Empty, scalar, multi-key AND, array OR, mixed, empty array, append-safety, SQL injection, AND-prefix |
| `TestBuildScopeFilter` | 8 | Single/multiple UUIDs, empty set, alias, no-alias, append-safety, AND-prefix |
| `TestMetadataFiltersSchema` | 4 | Dict acceptance on both request types, defaults, array values |
| `TestScopeArtifactIdSchema` | 3 | UUID acceptance on both request types, defaults |
| `TestParseMetadataFilters` | 8 | None, empty, valid JSON, arrays, malformed 400, non-dict 400, non-string 400, mixed-array 400 |

### Integration Performance Tests (7)

| Test | Assertion |
|------|-----------|
| `test_cte_returns_all_descendants` | 201 artifacts from project root ✓ |
| `test_cte_from_file_returns_file_and_chunks` | 20 artifacts (1 file + 19 chunks) ✓ |
| `test_cte_from_chunk_returns_only_self` | 1 artifact ✓ |
| `test_cte_nonexistent_scope_returns_empty` | 0 artifacts ✓ |
| `test_cte_tenant_isolation` | 0 artifacts with wrong tenant ✓ |
| `test_cte_performance_under_10ms` | Median 1.11ms < 10ms threshold ✓ |
| `test_cte_explain_plan` | Index scans confirmed, no seq scans ✓ |

---

## Consumer Impact

**For Developer1 and other API consumers:**

1. **No changes needed for existing integrations** — all new parameters default to their no-op values
2. **To use metadata filtering**: Add `metadata_filters` to your search requests (dict for POST, JSON string for GET)
3. **To use hierarchy scoping**: Add `scope_artifact_id` with the UUID of a project/file artifact to restrict results
4. **To paginate**: Add `offset` alongside your existing `limit` parameter
5. **Combine freely**: `metadata_filters` + `scope_artifact_id` + `offset` + `artifact_types` + `related_to` all compose correctly

---

## What's Next

Phase 1 is complete. The roadmap continues with:
- **Phase 2**: Deletion Infrastructure (soft-delete specs → schema migration → soft delete → physical delete)
- **Phase 3**: Unified Search Endpoint (`POST /search` with strategy inference)
- **Phase 4**: Advanced Graph Scoping (multi-hop traversal with depth control)