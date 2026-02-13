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
- [ ] Ensure `deleted_at IS NULL` filter is included in recursive CTE (forward-compatible with Phase 2) — deferred: column does not exist yet; filter will be added in Phase 2 migration
- [x] Add tests: scope to project returns only descendant chunks, scope to nonexistent artifact returns empty, scope respects tenant isolation
- [x] Performance test with realistic hierarchy (~200 artifacts, 3 levels) — 7/7 pass, median 1.16ms, p95 1.34ms, execution 2.6ms

---

## Phase 2: Deletion Infrastructure (Moderate risk — schema migration, new vocabulary column, mutable column on content table)

### 4. Soft-Delete Interaction Semantics (Specification — must be defined before implementation)
- [ ] Specify: `scope_artifact_id` pointing to a soft-deleted artifact returns empty results (the scope anchor must be active)
- [ ] Specify: recursive CTE for scoping excludes soft-deleted intermediate nodes (if a file artifact is soft-deleted, its child chunks are unreachable via scoping even if not themselves soft-deleted)
- [ ] Specify: `GET /artifacts/{id}` returns 404 for soft-deleted artifacts (default behavior)
- [ ] Specify: `GET /artifacts/{id}?include_deleted=true` returns soft-deleted artifacts (administrative use only)
- [ ] Specify: `GET /artifacts/{id}/children` excludes soft-deleted children by default
- [ ] Specify: embeddings of soft-deleted artifacts do NOT participate in semantic/vector search
- [ ] Specify: relations where source OR target is soft-deleted are excluded from relation queries and search scoping
- [ ] Specify: provenance events referencing soft-deleted artifacts remain visible (audit trail)
- [ ] Document all specifications in API documentation before deletion endpoints ship

### 5. Tenant Type Deletion Policy (Schema)
- [ ] Write migration: add `deletion_policy TEXT NOT NULL DEFAULT 'soft_delete'` column to `mimirdata.tenant_type`
- [ ] Update seed data: `environment` → `soft_delete`, `project` → `no_delete`, `experiment` → `physical_delete`
- [ ] Write migration: add `deleted_at TIMESTAMPTZ NULL` column to `mimirdata.artifact`
- [ ] Add index on `deleted_at` for efficient filtering: `CREATE INDEX idx_artifact_deleted ON mimirdata.artifact (deleted_at) WHERE deleted_at IS NOT NULL`
- [ ] Update tenant type schema (Pydantic) to include `deletion_policy` in response
- [ ] Update tenant service to expose `deletion_policy` when resolving tenant
- [ ] Write down migration for both changes
- [ ] Test migration up/down on clean database and on database with existing data

### 6. Soft Deletion (Standard Tenants)
- [ ] Implement `DELETE /artifacts/{id}` endpoint in artifacts router
- [ ] Implement tenant policy check: look up tenant type → deletion_policy; return 403 for `no_delete`
- [ ] Implement soft delete: set `deleted_at = now()` on target artifact
- [ ] Implement cascade soft delete: recursive `parent_artifact_id` traversal to set `deleted_at` on all descendants
- [ ] Return 409 Conflict when `cascade=false` and artifact has active (non-deleted) children
- [ ] Return 404 for already-deleted artifacts
- [ ] Update all artifact retrieval queries: add `WHERE deleted_at IS NULL`
- [ ] Update all search queries: add `WHERE a.deleted_at IS NULL` (fulltext, semantic, hybrid, similar)
- [ ] Update relation queries: exclude relations where source or target artifact is soft-deleted
- [ ] Update embedding queries: exclude embeddings for soft-deleted artifacts
- [ ] Update context service: exclude soft-deleted artifacts from context traversal
- [ ] Provenance events are NOT affected — they remain as audit trail
- [ ] Add tests: soft delete single artifact, cascade soft delete tree, 403 on audited tenant, 409 without cascade when children exist, search excludes soft-deleted, relations exclude soft-deleted

### 7. Physical Deletion (Sandbox/Experiment Tenants)
- [ ] Implement physical delete path in artifact service for `physical_delete` policy tenants
- [ ] Delete embeddings first: query all `mimir_vectors.vec_{type}` tables for the artifact's embeddings; delete rows
- [ ] Delete relations: remove rows from relation table where artifact is source OR target
- [ ] Delete provenance events: remove rows from provenance_event table for the artifact
- [ ] Delete the artifact row itself
- [ ] Implement cascade physical delete: depth-first recursive traversal of `parent_artifact_id` tree, deleting leaf nodes before parents (respects FK ordering)
- [ ] Ensure cascade cannot cross tenant boundaries: `AND tenant_id = %s` at every level
- [ ] Return deletion counts in response: `{"deleted": {"artifacts": N, "embeddings": N, "relations": N, "provenance_events": N}}`
- [ ] Add tests: physical delete single artifact, cascade physical delete tree, verify no rows remain in any table, verify tenant isolation, verify FK ordering (leaf-first)
- [ ] Stress test: cascade delete of ~200 artifact tree with embeddings across multiple vector tables

---

## Phase 3: Search Unification (High risk — breaking API change, complex validation, deprecation management)

### 8. Unified Search Endpoint (`POST /search`)
- [ ] Design unified search request schema with discriminated ranking strategy
- [ ] Define validation rules: which parameter combinations map to which strategy (see evaluation doc table)
- [ ] Define error cases: ambiguous combinations (`query_vector` + `similar_to`), missing ranking input, missing `embedding_type` when required
- [ ] Implement strategy inference logic with clear error messages ("Your request was interpreted as semantic search because you provided `query_vector`; `embedding_type` is required for this strategy")
- [ ] Implement `POST /search` router, delegating to existing service functions based on inferred strategy
- [ ] Include all Phase 1-3 features in unified schema: `metadata_filters`, `scope_artifact_id`, `offset`, `artifact_types`
- [ ] Add deprecation headers to existing four search endpoints
- [ ] Add tests: each ranking strategy via unified endpoint, validation error cases, all filter combinations work uniformly
- [ ] Update OpenAPI documentation
- [ ] Communicate deprecation timeline to consumers
- [ ] Monitor usage of deprecated endpoints; remove in future major version after migration confirmed

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
