# Enhancement Roadmap — Implementation Checklist

**Author**: Mimir Architecture Team  
**Date**: 2026-02-13  
**Ordering Principle**: Least controversial / lowest risk first, increasing in architectural risk. Each item builds on or is independent of the items above it.  
**Source**: [Enhancement Request Evaluation](enhancement-request-evaluation.md)

---

## Phase 1: Search Infrastructure (No architectural risk — additive, backward-compatible)

> **Rationale for grouping**: Developer1's feedback (2026-02-13 response) correctly identified that scoping and metadata filtering are jointly necessary for correct search. Scoping without metadata filtering still returns wrong-type chunks within the correct project scope. Metadata filtering without scoping still has cross-project contamination. Pagination correctness depends on server-side filtering. All three ship together.

### 1. Pagination on All Search Types
- [x] Add `offset` parameter to semantic search endpoint schema and router
- [x] Add `offset` parameter to hybrid search endpoint schema and router
- [x] Add `offset` parameter to similar search endpoint schema and router
- [x] Update search service query construction to include `OFFSET` for all search types
- [x] Document performance characteristics (deep offset pagination degrades on HNSW)
- [x] Add tests for offset behavior on each search type

### 2. Metadata Filtering on Search
- [x] Design `metadata_filters` schema: dict of key → value|list, AND across keys, OR within arrays
- [x] Design filter contract for future extensibility: scalar/array values mean positive match; reserve object wrapper (e.g., `{"not": "value"}`) for future negation support without breaking existing consumers
- [x] Add `metadata_filters` parameter to all four search endpoint schemas
- [x] Implement JSONB filtering in search service using parameterized queries (no string interpolation of keys/values)
- [x] Verify GIN index utilization for containment queries; document query patterns that fall back to sequential scan
- [x] Add tests: single key match, multi-key AND, array OR, empty filters (no-op), nonexistent key (empty results)
- [x] Document scope limitations: no negation, no range queries, no nested metadata (with note that contract is designed for future negation extension)

### 3. Parent-Child Hierarchy Scoping
- [x] Add `scope_artifact_id` parameter (optional UUID) to all four search endpoint schemas
- [x] Implement recursive CTE on `parent_artifact_id` to resolve descendant artifact IDs for a given scope anchor
- [x] Integrate descendant ID set as a WHERE clause in fulltext search query
- [x] Integrate descendant ID set as a WHERE clause in semantic search query (join against vector table)
- [x] Integrate descendant ID set as a WHERE clause in hybrid search query
- [x] Integrate descendant ID set as a WHERE clause in similar search query
- [x] Ensure recursive CTE includes `AND tenant_id = %s` at every level (multi-tenant safety)
- [x] Ensure `deleted_at IS NULL` filter is included in recursive CTE — implemented in Phase 2 (migration 006 adds column, search_service.py updated)
- [x] Add tests: scope to project returns only descendant chunks, scope to nonexistent artifact returns empty, scope respects tenant isolation
- [x] Performance test with realistic hierarchy (~200 artifacts, 3 levels) — 7/7 pass, median 1.16ms, p95 1.34ms, execution 2.6ms

---

## Phase 2: Deletion Infrastructure (Moderate risk — schema migration, new vocabulary column, mutable column on content table)

### 4. Soft-Delete Interaction Semantics (Specification — must be defined before implementation)
- [x] Specify: `scope_artifact_id` pointing to a soft-deleted artifact returns empty results (the scope anchor must be active)
- [x] Specify: recursive CTE for scoping excludes soft-deleted intermediate nodes (if a file artifact is soft-deleted, its child chunks are unreachable via scoping even if not themselves soft-deleted)
- [x] Specify: `GET /artifacts/{id}` returns 404 for soft-deleted artifacts (default behavior)
- [x] Specify: `GET /artifacts/{id}?include_deleted=true` returns soft-deleted artifacts (administrative use only)
- [x] Specify: `GET /artifacts/{id}/children` excludes soft-deleted children by default
- [x] Specify: embeddings of soft-deleted artifacts do NOT participate in semantic/vector search
- [x] Specify: relations where source OR target is soft-deleted are excluded from relation queries and search scoping
- [x] Specify: provenance events referencing soft-deleted artifacts remain visible (audit trail)
- [x] Document all specifications in API documentation before deletion endpoints ship — see `docs/soft-delete-semantics.md`

### 5. Tenant Type Deletion Policy (Schema)
- [x] Write migration: add `deletion_policy TEXT NOT NULL DEFAULT 'soft_delete'` column to `mimirdata.tenant_type` — `006_deletion_infrastructure.up.sql`
- [x] Update seed data: `environment` → `soft_delete`, `project` → `no_delete`, `experiment` → `physical_delete`
- [x] Write migration: add `deleted_at TIMESTAMPTZ NULL` column to `mimirdata.artifact`
- [x] Add index on `deleted_at` for efficient filtering: `CREATE INDEX idx_artifact_deleted ON mimirdata.artifact (deleted_at) WHERE deleted_at IS NOT NULL`
- [x] Update tenant type schema (Pydantic) to include `deletion_policy` in response — `TenantResponse.deletion_policy`
- [x] Update tenant service to expose `deletion_policy` when resolving tenant — `tenant_service.get_deletion_policy()`
- [x] Write down migration for both changes — `006_deletion_infrastructure.down.sql`
- [x] Test migration up/down on clean database and on database with existing data — verified round-trip down/up on database with 925+ existing artifacts

### 6. Soft Deletion (Standard Tenants)
- [x] Implement `DELETE /artifacts/{id}` endpoint in artifacts router
- [x] Implement tenant policy check: look up tenant type → deletion_policy; return 403 for `no_delete`
- [x] Implement soft delete: set `deleted_at = now()` on target artifact
- [x] Implement cascade soft delete: recursive `parent_artifact_id` traversal to set `deleted_at` on all descendants
- [x] Return 409 Conflict when `cascade=false` and artifact has active (non-deleted) children
- [x] Return 404 for already-deleted artifacts
- [x] Update all artifact retrieval queries: add `WHERE deleted_at IS NULL`
- [x] Update all search queries: add `WHERE a.deleted_at IS NULL` (fulltext, semantic, hybrid, similar)
- [x] Update relation queries: exclude relations where source or target artifact is soft-deleted
- [x] Update embedding queries: exclude embeddings for soft-deleted artifacts
- [x] Update context service: exclude soft-deleted artifacts from context traversal — relation traversal JOINs exclude soft-deleted endpoints
- [x] Provenance events are NOT affected — they remain as audit trail
- [x] Add tests: soft delete single artifact, cascade soft delete tree, 403 on audited tenant, 409 without cascade when children exist, search excludes soft-deleted, relations exclude soft-deleted — `tests/integration/test_deletion_phase2.py`

### 7. Physical Deletion (Sandbox/Experiment Tenants)
- [x] Implement physical delete path in artifact service for `physical_delete` policy tenants
- [x] Delete embeddings first: query all `mimir_vectors.vec_{type}` tables for the artifact's embeddings; delete rows
- [x] Delete relations: remove rows from relation table where artifact is source OR target
- [x] Delete provenance events: remove rows from provenance_event table for the artifact
- [x] Delete the artifact row itself
- [x] Implement cascade physical delete: depth-first recursive traversal of `parent_artifact_id` tree, deleting leaf nodes before parents (respects FK ordering)
- [x] Ensure cascade cannot cross tenant boundaries: `AND tenant_id = %s` at every level
- [x] Return deletion counts in response: `{"deleted": {"artifacts": N, "embeddings": N, "relations": N, "provenance_events": N}}`
- [x] Add tests: physical delete single artifact, cascade physical delete tree, verify truly gone (include_deleted=true also 404) — `tests/integration/test_deletion_phase2.py`
- [x] Stress test: cascade delete of ~201 artifact tree — soft-delete 201 artifacts in 11ms, physical-delete 201 artifacts + 5 relations in 31ms

---

## Phase 3: Search Unification (High risk — breaking API change, complex validation, deprecation management)

### 8. Unified Search Endpoint (`POST /search`)
- [x] Design unified search request schema with discriminated ranking strategy — `UnifiedSearchRequest` in `schemas/search.py`, `SearchStrategy` enum
- [x] Define validation rules: which parameter combinations map to which strategy (see evaluation doc table) — 8-row inference table in `_infer_search_strategy()`
- [x] Define error cases: ambiguous combinations (`query_vector` + `similar_to`), missing ranking input, missing `embedding_type` when required — `AMBIGUOUS_RANKING`, `RESERVED_COMBINATION`, `NO_RANKING_INPUT`, `MISSING_EMBEDDING_TYPE`
- [x] Implement strategy inference logic with clear error messages ("Your request was interpreted as semantic search because you provided `query_vector`; `embedding_type` is required for this strategy") — pure function `_infer_search_strategy()` in `routers/search.py`
- [x] Implement `POST /search` router, delegating to existing service functions based on inferred strategy — `unified_search()` with `_execute_fulltext/semantic/hybrid/similar()` delegation
- [x] Include all Phase 1-3 features in unified schema: `metadata_filters`, `scope_artifact_id`, `offset`, `artifact_types` — all fields present in `UnifiedSearchRequest`
- [x] Add deprecation headers to existing four search endpoints — `Deprecation: true`, `Sunset: 2026-08-01`, `Link: </search>; rel="successor-version"`
- [x] Add tests: each ranking strategy via unified endpoint, validation error cases, all filter combinations work uniformly — 27 unit tests (pure inference + schema), integration tests for HTTP-level validation and deprecation headers
- [x] Update OpenAPI documentation — API version bumped to v3.0.0, legacy endpoints marked `deprecated=True`
- [x] Remove legacy endpoints: `POST /search/semantic`, `POST /search/hybrid`, `GET /search/similar/{id}` — removed from router, dead schemas deleted
- [x] Retain `GET /search/fulltext` as deprecated GET convenience — deprecation headers present
- [x] Migrate Phase 1 unit tests from legacy schemas to `UnifiedSearchRequest`
- [x] Remove dead `SemanticSearchRequest` and `HybridSearchRequest` schema classes
- [x] Clean up `schemas/__init__.py` exports
- [x] Communicate deprecation timeline to consumers (fulltext GET endpoint) — see `comms/06_v3_migration_guide.md`

---

## Phase 4: Advanced Graph (Highest risk — cycle detection, performance unpredictability, query complexity)

### 9. General Graph Scoping with Depth Control
- [ ] Design `depth` parameter for existing `related_to` search filter (values: integer or `"recursive"`)
- [ ] Implement multi-hop relation traversal in search service with configurable depth
- [ ] Implement cycle detection (visited set) to prevent infinite loops in symmetric/cyclic relations
- [ ] Implement maximum depth limit (system-configured) to prevent runaway queries
- [ ] Implement fan-out limit: cap the candidate set size from traversal to prevent memory exhaustion
- [ ] Add query timeout for traversal to bound worst-case performance
- [ ] Integrate traversal result set as WHERE clause in all search types
- [ ] Consider materialized path or closure table if traversal performance is insufficient
- [ ] Add tests: depth=1 (existing behavior), depth=2 multi-hop, recursive traversal, cycle detection, fan-out limits, timeout behavior
- [ ] Performance test with realistic graph density

---

## Summary

| # | Item | Risk | Phase | Depends On |
|---|---|---|---|---|
| 1 | Pagination on all search types | None | 1 | — |
| 2 | Metadata filtering | Low | 1 | — |
| 3 | Parent-child hierarchy scoping | Low | 1 | — |
| 4 | Soft-delete interaction semantics (spec) | None (documentation) | 2 | — |
| 5 | Tenant type deletion policy (schema) | Moderate | 2 | #4 |
| 6 | Soft deletion | Moderate | 2 | #5 |
| 7 | Physical deletion with cascade | Moderate-High | 2 | #5, #6 |
| 8 | Unified search endpoint | High | 3 | #1, #2, #3 |
| 9 | General graph scoping with depth | Highest | 4 | #3, #8 (recommended) |

---

## Changelog

| Date | Change | Reason |
|---|---|---|
| 2026-02-13 | Initial roadmap | — |
| 2026-02-13 | Merged metadata filtering + scoping into Phase 1; added soft-delete semantics specification; renumbered phases | Developer1 response: scoping + metadata filtering are jointly necessary for correct search; soft-delete interaction semantics need specification before deletion ships |
| 2026-02-13 | Phase 2 implementation complete (Items 4-7) | Migration 006, soft-delete/physical-delete services, DELETE endpoint, query exclusion across all services, API integration tests |
| 2026-02-13 | Phase 3 implementation complete (Item 8, coding) | `POST /search` unified endpoint, `SearchStrategy` enum, `UnifiedSearchRequest` schema, strategy inference, deprecation headers on legacy endpoints, v3.0.0 |
| 2026-02-13 | Phase 3 endpoint removal | Removed `POST /search/semantic`, `POST /search/hybrid`, `GET /search/similar/{id}`. Deleted `SemanticSearchRequest`, `HybridSearchRequest`. Retained `GET /search/fulltext` (deprecated). |
| 2026-02-13 | Phase 3 complete | Consumer migration guide published (`comms/06_v3_migration_guide.md`). All Phase 3 items done. |
