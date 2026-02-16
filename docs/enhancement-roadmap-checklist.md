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

## Phase 4: Graph Traversal Engine (v4.0.0) ✅

> **Implementation**: Apache AGE 1.7.0 Cypher-based graph engine replacing Python BFS.
> See `docs/graph-engine-technical-design.md`, `docs/graph-engine-agreed-approach.md`, `docs/graph-engine-development-checklist.md`.

### 9. Graph Engine Foundation
- [x] AGE Cypher spike — validated VLP queries, agtype parsing, AGE 1.7.0 capabilities (7/8 tests passed)
- [x] agtype parser — pure-function parser for AGE's `agtype` return type (`::vertex`/`::edge` suffix stripping + JSON)
- [x] Graph engine core (`graph_engine.py`) — `traverse()` and `find_paths()` using Cypher VLP queries
- [x] Cypher builders — pure functions generating parameterized Cypher for outgoing/incoming/both directions
- [x] Python-side relation type filtering (AGE 1.7.0 lacks `ALL()` predicate)
- [x] Full relation path data in traversal results (D3 — stakeholder requirement for argument chain validation)

### 10. Graph Scoping with Depth Control
- [x] Design `GraphScope` schema with `root_artifact_id`, `max_depth`, `relation_types`, `direction`
- [x] Implement configurable depth traversal via Cypher VLP `*1..N` range pattern
- [x] Implement cycle prevention — AGE's VLP naturally avoids revisiting edges; Python deduplication by artifact_id
- [x] Implement maximum depth ceiling — `MIMIR_GRAPH_MAX_DEPTH` (default 10, configurable)
- [x] Implement fan-out limit — `MIMIR_GRAPH_MAX_RESULT_SET` (default 500) → `GraphScopeTooLargeError` (HTTP 422)
- [x] Implement query timeout — `SET LOCAL statement_timeout` per query (D6) → `GraphQueryTimeoutError` (HTTP 504)
- [x] Integrate traversal result set as post-filter on all search strategies (traverse-then-search pattern)
- [x] `graph_scope` parameter on `POST /search` — mutually exclusive with `scope_artifact_id`
- [x] `scope_artifact_id` backward compatibility — internally converts to `GraphScope(max_depth=1, direction="both")`

### 11. Context Service Migration
- [x] Replace Python BFS (N+1 SQL queries per hop) with single `graph_engine.traverse()` Cypher query
- [x] Map policy configs (DIRECT_RELATIONS, DERIVED_LINEAGE, EVIDENCE_CHAIN, FULL_GRAPH) to traverse parameters
- [x] Preserve `relation_path` and `distance` in ContextArtifact response

### 12. Graph Engine Testing
- [x] 48 unit tests: agtype parser (24), Cypher builders + path extraction + filtering (24)
- [x] 14 integration tests: traversal with known 6-node graph topology
- [x] 8 integration tests: graph-scoped search (fulltext, depth control, relation filtering, backward compat, validation)
- [x] Error handling tests: `GraphScopeTooLargeError`, `GraphNotFoundError`, timeout enforcement

---

## Phase 5: Graph Engine Extensions (Future — deferred items from D4 and design doc)

> **Status**: Not started. Items below were explicitly deferred during Phase 4 design review.

### 13. Match Pattern Queries (D4 — deferred to Phase 5+)
- [ ] Design `MatchPattern` schema for structured graph pattern matching
- [ ] Implement Cypher pattern builder for arbitrary multi-hop typed patterns
- [ ] Support compound patterns (e.g., "A -[derived_from]-> B -[supports]-> C")
- [ ] Add validation for pattern syntax and depth limits
- [ ] Integration tests with complex pattern topologies

### 14. Graph-Aware Relevance Scoring
- [ ] Design relevance scoring that combines graph distance with text/semantic scores
- [ ] Implement weighted scoring: closer graph neighbors score higher
- [ ] Integrate with hybrid search RRF algorithm
- [ ] A/B testing framework for scoring tuning

### 15. Graph Analytics Endpoints
- [ ] `GET /graph/stats` — vertex/edge counts per tenant graph
- [ ] `GET /graph/neighbors/{artifact_id}` — direct neighbor listing with counts by type
- [ ] Graph visualization data endpoint (nodes + edges for UI rendering)

### 16. Performance Optimization
- [ ] Evaluate AGE 1.8+ features (ALL() predicate, shortestPath()) when available
- [ ] Consider materialized path or closure table if Cypher VLP performance is insufficient at scale
- [ ] Benchmark traversal performance with realistic graph density (1000+ nodes, 5000+ edges)
- [ ] Evaluate pre-computed scope caching for frequently-queried root artifacts

---

## Summary

| # | Item | Risk | Phase | Status | Depends On |
|---|---|---|---|---|---|
| 1 | Pagination on all search types | None | 1 | ✅ | — |
| 2 | Metadata filtering | Low | 1 | ✅ | — |
| 3 | Parent-child hierarchy scoping | Low | 1 | ✅ | — |
| 4 | Soft-delete interaction semantics (spec) | None (documentation) | 2 | ✅ | — |
| 5 | Tenant type deletion policy (schema) | Moderate | 2 | ✅ | #4 |
| 6 | Soft deletion | Moderate | 2 | ✅ | #5 |
| 7 | Physical deletion with cascade | Moderate-High | 2 | ✅ | #5, #6 |
| 8 | Unified search endpoint | High | 3 | ✅ | #1, #2, #3 |
| 9 | Graph engine foundation | High | 4 | ✅ | #8 |
| 10 | Graph scoping with depth control | High | 4 | ✅ | #9 |
| 11 | Context service migration | Moderate | 4 | ✅ | #9 |
| 12 | Graph engine testing | — | 4 | ✅ | #9, #10, #11 |
| 13 | Match pattern queries | High | 5 | 🔮 | #9 |
| 14 | Graph-aware relevance scoring | Moderate | 5 | 🔮 | #10 |
| 15 | Graph analytics endpoints | Low | 5 | 🔮 | #9 |
| 16 | Performance optimization | Moderate | 5 | 🔮 | #10 |

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
| 2026-02-15 | Phase 4 implementation complete (Items 9-12) | Graph traversal engine via Apache AGE 1.7.0. Cypher VLP queries replace Python BFS. `graph_scope` on POST /search. Context service migrated. v4.0.0. |
| 2026-02-15 | Phase 5 defined (Items 13-16) | Deferred items from Phase 4 design review: MatchPattern (D4), graph-aware scoring, analytics endpoints, performance optimization. |
