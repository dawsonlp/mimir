# Design Document: Evaluation of Developer1 Enhancement Requests

**Author**: Mimir Architecture Team  
**Date**: 2026-02-13  
**Status**: Draft — For Review  
**Audience**: Mimir maintainers, Developer1 team, future integration consumers

---

## Executive Summary

Developer1, Mimir's first integration consumer, has submitted an enhancement request based on real production issues encountered during automated code evaluation of a 132-file Python project. The request contains six items across three priority tiers. This document evaluates each request against Mimir's architectural principles, identifies tensions and risks, and recommends a path forward.

The requests are well-motivated and well-documented. Two represent genuine gaps that must be addressed. One proposes a fundamental change to a core architectural invariant that requires careful deliberation. One proposes a major API restructuring with strong arguments but significant migration cost.

---

## Table of Contents

1. [Request 1: Cascade Artifact Deletion](#1-cascade-artifact-deletion)
2. [Request 2: Unified Search Endpoint](#2-unified-search-endpoint)
3. [Request 3: Metadata Filtering](#3-metadata-filtering)
4. [Request 4: Graph Scoping on Search](#4-graph-scoping-on-search)
5. [Request 5: Pagination on All Ranking Types](#5-pagination-on-all-ranking-types)
6. [Request 6: Parent Expansion on Search Results](#6-parent-expansion-on-search-results)
7. [Cross-Cutting Concerns](#cross-cutting-concerns)
8. [Recommended Priority and Sequencing](#recommended-priority-and-sequencing)

---

## 1. Cascade Artifact Deletion

### Developer1's Request

Add `DELETE /artifacts/{id}` with optional `?cascade=true` to delete artifacts and their descendants, embeddings, and relations. Motivated by inability to clean up 6,006 accidentally ingested artifacts that permanently pollute search results.

### Architectural Tension: The Append-Only Invariant

This is the most architecturally significant request. Mimir's core architecture document states:

> **Principle 3: Append-Only Content** — Content tables (artifact, relation, embedding, provenance) support INSERT only. No UPDATE, no DELETE.

This invariant was a deliberate design choice, not an oversight. Append-only semantics provide:

- **Auditability**: Every artifact ever created is preserved, enabling full provenance reconstruction.
- **Referential safety**: No dangling references from relations, embeddings, or provenance events pointing to deleted artifacts.
- **Simplicity**: No cascade logic, no orphan detection, no soft-delete state machines.
- **Concurrency safety**: No readers can encounter a "deleted from under them" race condition.

Developer1's request directly contradicts this principle. The question is whether the principle should be relaxed, and if so, under what constraints.

### Analysis: The Problem Is Real

Developer1's situation — 6,006 permanently irremovable garbage artifacts dominating every search — is a genuine operational crisis with no workaround. The append-only invariant, while architecturally clean, creates a system that is:

- **Unrecoverable from ingestion errors**: A single bad pipeline run permanently degrades search quality.
- **Hostile to iterative development**: Every experiment, test run, and debugging session leaves permanent artifacts.
- **Incompatible with data lifecycle requirements**: GDPR, data retention policies, and storage management all require deletion capability.

The append-only design assumed that all data entering Mimir would be curated and intentional. Developer1's experience demonstrates that in practice, automated pipelines will make mistakes, and the system must tolerate and recover from them.

### Resolution: Tenant-Type-Scoped Deletion Policy

Rather than relaxing the append-only invariant system-wide, the correct approach is to recognize that **deletion policy is a property of the tenant type, not a system-wide setting.** The append-only invariant was always the right policy for production/compliance data. It was the wrong policy for *all* data.

Mimir's `tenant_type` vocabulary table already provides the semantic hook. Today it seeds three types (`environment`, `project`, `experiment`), but these are placeholder categories. What's needed is a policy dimension on tenant types that governs data lifecycle behavior.

#### Tenant Type Deletion Tiers

| Tenant Type | Deletion Behavior | Audit Posture | Use Case |
|---|---|---|---|
| `sandbox` | Physical deletion with cascade permitted | Minimal — provenance events deleted with artifacts | Dev iteration, experiments, throwaway pipeline runs |
| `standard` | Soft deletion only (`deleted_at` timestamp) | Standard — provenance preserved, data logically removed | Working environments, staging, integration testing |
| `audited` | No deletion permitted — 403 Forbidden | Full — append-only invariant strictly enforced | Production compliance, regulated data, legal hold |

The `DELETE /artifacts/{id}` endpoint behavior is determined by the tenant's type:

- **`sandbox` tenant**: Physical deletion. Rows removed from artifact, embedding (across dynamic vector tables), relation, and provenance tables. Cascade via `?cascade=true` removes all descendants. This directly addresses Developer1's scenario — create a sandbox tenant for pipeline iteration, delete freely.
- **`standard` tenant**: Soft deletion. Sets `deleted_at` on the artifact (and descendants when cascading). Data excluded from search and retrieval but preserved for audit. Recoverable via an undelete mechanism if needed.
- **`audited` tenant**: Deletion refused. The endpoint returns 403 with a clear error: "Deletion is not permitted for audited tenants." The append-only invariant holds absolutely.

#### Why This Is Better Than System-Wide Soft Delete

The original draft of this document recommended system-wide soft deletion. The tenant-scoped approach is superior for several reasons:

1. **The invariant is preserved where it matters.** Audited tenants are truly append-only, exactly as the architecture document intended. There is no "controlled relaxation" — the invariant holds for the tenants that need it.

2. **Developer1's problem has an immediate workaround.** Before deletion ships, Developer1 can create a new tenant (type: sandbox or experiment), re-ingest their 132 files there, and search against the clean tenant. The contaminated tenant can be purged later.

3. **No ambiguity about what "deleted" means.** In a sandbox tenant, deleted means gone. In a standard tenant, deleted means logically removed but auditable. In an audited tenant, deletion doesn't exist. The consumer knows exactly what they're getting based on which tenant they chose.

4. **Deployment-model independent.** Whether Mimir runs as a shared multi-tenant instance or as a dedicated container-per-environment, the policy travels with the tenant type. A team can have a sandbox and an audited tenant in the same Mimir instance, or in separate containers — the behavior is identical.

#### Schema Changes

**`tenant_type` vocabulary table**: Add a `deletion_policy` column:

| Column | Type | Values |
|---|---|---|
| `deletion_policy` | `TEXT NOT NULL DEFAULT 'soft_delete'` | `'physical_delete'`, `'soft_delete'`, `'no_delete'` |

This is a vocabulary/admin table (mutable), so adding a column does not violate the append-only invariant on content tables.

**`artifact` table**: Add `deleted_at TIMESTAMPTZ NULL` column for soft-delete support in `standard` tenants.

**Existing `tenant_type` seed data update**:

| code | deletion_policy |
|---|---|
| `environment` | `soft_delete` |
| `project` | `no_delete` |
| `experiment` | `physical_delete` |

New seed types can be added as needed (e.g., `sandbox` with `physical_delete`, `audited` with `no_delete`).

#### Endpoint Behavior

The `DELETE /artifacts/{id}` endpoint:

1. Resolves the tenant from the `X-Tenant-ID` header
2. Looks up the tenant's type and its `deletion_policy`
3. Based on policy:
   - `no_delete` → Return 403 Forbidden: `{"detail": "Deletion not permitted for this tenant type", "code": "DELETION_NOT_PERMITTED"}`
   - `soft_delete` → Set `deleted_at = now()` on the artifact. With `?cascade=true`, recursively set `deleted_at` on all descendants via `parent_artifact_id` traversal. Return 409 Conflict without cascade if artifact has active children.
   - `physical_delete` → Physically remove the artifact row and associated embeddings (across dynamic vector tables), relations (both as source and target), and provenance events. With `?cascade=true`, recursively delete all descendants first (depth-first to respect foreign key ordering).

All search, retrieval, and relation queries must include `WHERE a.deleted_at IS NULL` to exclude soft-deleted artifacts.

#### Impact on Existing Components

- **`tenant_type` table**: Add `deletion_policy` column (admin table, mutable)
- **`artifact` table**: Add `deleted_at TIMESTAMPTZ NULL` column
- **All search queries**: Add `WHERE a.deleted_at IS NULL` predicate
- **Artifact retrieval**: Exclude soft-deleted artifacts by default
- **Relations**: Exclude relations involving soft-deleted artifacts from traversal
- **Embeddings**: Exclude embeddings for soft-deleted artifacts from vector search
- **Provenance**: In `soft_delete` tenants, provenance events are preserved. In `physical_delete` tenants, provenance events for deleted artifacts are also removed.
- **Migration**: Non-breaking — new nullable column on artifact, new column on vocabulary table

---

## 2. Unified Search Endpoint

### Developer1's Request

Replace the four search endpoints (`/search/fulltext`, `/search/semantic`, `/search/hybrid`, `/search/similar/{id}`) with a single `POST /search` endpoint where the ranking strategy is determined by which parameters are provided.

### Analysis: The Argument Is Strong but the Cost Is High

Developer1's argument is architecturally sound. The observation that four endpoints sharing 80% of their parameters is "a code smell in an API just as it is in application code" is correct. The current inconsistencies (relation-aware filtering exists on all four endpoints per P2, but pagination only on fulltext; metadata filtering on none) are a direct consequence of having separate endpoints that evolved independently.

The Elasticsearch `_search` precedent is apt. Single-endpoint-with-discriminated-body is a proven pattern for search APIs.

#### Advantages of Unification

1. **Structural prevention of feature gaps**: New filtering capabilities are added once and apply to all ranking strategies.
2. **Composability**: Combinations like "similar + fulltext re-ranking" become possible without new endpoints.
3. **Simpler client integration**: One method, one schema, progressive disclosure.
4. **Reduced API surface maintenance**: One router, one schema, one service entry point.

#### Risks and Concerns

1. **Breaking change**: This is a v3-level API change. All existing consumers (Developer1 included) must migrate. The four existing endpoints are documented, tested, and in use.

2. **Implicit routing complexity**: The "ranking strategy emerges from what the consumer provides" pattern is elegant but introduces ambiguity. What happens when a consumer provides `query` + `query_vector` + `similar_to`? Is that an error, or a three-way hybrid? The dispatch logic must be clearly defined and well-documented, or consumers will encounter surprising behavior.

3. **Validation complexity**: Each ranking strategy has different required parameters. A single schema must express "if `query_vector` is provided, `embedding_type` is required; if only `query` is provided, `embedding_type` is optional." This is achievable but requires careful schema design with discriminated unions or post-validation logic.

4. **Testing surface**: One endpoint with N ranking strategies × M filter combinations is harder to test exhaustively than N endpoints with simpler contracts.

5. **Error messaging**: When a request fails validation, the error must explain which ranking strategy was inferred and why it failed. "Missing `embedding_type`" is less helpful than "Semantic search requires `embedding_type` — your request was interpreted as semantic because you provided `query_vector`."

### Recommendation

**Accept the unified search endpoint as a design goal for the next major version, but implement it as an additive endpoint alongside the existing four during a transition period.**

Specifically:
1. Add `POST /search` as a new endpoint implementing the unified contract.
2. Deprecate (but do not remove) the four existing endpoints. They continue to work but return a deprecation header.
3. Internally, the unified endpoint delegates to the same service functions the individual endpoints use. This is a routing/schema change, not a search algorithm change.
4. After a migration period (defined by when all known consumers have migrated), remove the deprecated endpoints in a future major version.

This avoids a breaking change while moving toward the correct architecture.

### Contract Constraints for the Unified Endpoint

The unified search request must enforce these rules:

| Parameters Provided | Inferred Strategy | Additional Requirements |
|---|---|---|
| `query` only | Fulltext | None |
| `query_vector` | Semantic | `embedding_type` required |
| `query` + `query_vector` | Hybrid | `embedding_type` required |
| `similar_to` | Similar | `embedding_type` required |
| `similar_to` + `query` | Similar with fulltext re-rank | `embedding_type` required |
| `query_vector` + `similar_to` | Error: ambiguous | — |
| None of the above | Error: no ranking input | — |

The `semantic_weight` parameter should only be accepted when hybrid is inferred (both `query` and `query_vector` provided). Providing it without both should produce a validation warning or be silently ignored.

### Developer1's Design Observations Worth Preserving

Developer1's note that "embedding generation is the client's job" correctly validates Mimir's architecture. Mimir stores and indexes vectors; it does not generate them. This principle should be explicitly documented and preserved through the unified endpoint design. The unified endpoint should accept `query_vector` (pre-computed) and never accept a `query_text` parameter that would imply server-side embedding generation.

---

## 3. Metadata Filtering

### Developer1's Request

Add `metadata_filters` to search that enables server-side filtering by arbitrary metadata fields stored on artifacts, with AND semantics across keys and OR semantics for array values within a key.

### Analysis

This is a well-scoped, high-value enhancement with no architectural tension.

#### Advantages

- **Solves the pagination problem**: Client-side post-filtering breaks `limit`/`offset` semantics, as Developer1 correctly identifies. If a consumer requests 10 results but 7 are filtered out client-side, they get 3 usable results. Server-side filtering ensures `limit` means what it says.
- **Leverages existing data**: The `metadata` JSONB column on the artifact table already exists and is indexed (GIN index). No schema changes required.
- **General utility**: Every consumer will have metadata-based filtering needs. This is not specific to Developer1's use case.

#### Concerns

1. **Query performance**: JSONB filtering with arbitrary keys can be expensive depending on the query pattern. The existing GIN index on `metadata` supports containment queries (`@>`) efficiently, but arbitrary key-value matching with OR semantics may require careful query construction to use the index.

2. **SQL injection surface**: Metadata keys are consumer-defined strings that will appear in query construction. The service layer must parameterize these carefully, never interpolating metadata keys or values into SQL strings.

3. **Semantic clarity**: The proposed AND-across-keys, OR-within-arrays contract is intuitive but limited. It does not support negation ("NOT chunk_type = header"), range queries ("created_after > 2026-01-01"), or nested metadata. These limitations should be explicitly documented as out of scope for the initial implementation.

### Recommendation

**Accept this enhancement.** Implement metadata filtering as part of the search contract (whether unified or per-endpoint). The filter semantics proposed by Developer1 (AND across keys, OR within array values) are a reasonable starting point.

The filtering should be implemented using PostgreSQL's JSONB containment operators where possible for index utilization. For OR-within-array semantics, the query will need to construct `metadata->>'key' IN (...)` clauses rather than pure containment checks.

### Scope Boundary

Metadata filtering is a WHERE clause on the candidate set. It does not affect ranking or scoring. This distinction must be preserved — filtering narrows results, ranking orders them.

---

## 4. Graph Scoping on Search

### Developer1's Request

Add a `scope` parameter to search that restricts results to a subgraph anchored at a specific artifact, with configurable relation types, direction, and depth (including recursive traversal for parent-child hierarchies).

### Current State

Mimir already has relation-aware search filtering (implemented as P2 in the enhancement roadmap). All four search endpoints accept `related_to`, `relation_type`, and `relation_direction` parameters. These provide single-hop scoping: "find artifacts directly related to artifact X via relation type Y."

What's missing:
- **Recursive depth**: Cannot scope to "all descendants of artifact X" (multi-hop)
- **Parent-child hierarchy awareness**: The `parent_artifact_id` column provides a direct tree structure that could be traversed without using the relation table at all

### Analysis

Developer1's distinction between **scoping** (WHERE clause on candidates) and **graph traversal** (multi-hop query language) is architecturally sound and should be adopted.

#### The Parent-Child Hierarchy Is Special

The `parent_artifact_id` column on the artifact table creates a tree structure that is more efficient to traverse than the general relation graph. For Developer1's primary use case — "search only within this project's artifacts" — the scoping query is:

> Find all artifacts where `parent_artifact_id` traces back to the project artifact through any number of ancestors.

This can be implemented as a recursive CTE on the artifact table alone, without touching the relation table. This is significantly more efficient than traversing `parent_of` relations, which require joining through the relation table.

#### Recursive Relation Traversal Is Complex

General recursive traversal through the relation table (follow edges of type X to depth N) is substantially more complex:
- Must handle cycles (A → B → A)
- Must handle fan-out explosion (each hop can multiply the candidate set)
- Performance is unpredictable depending on graph density
- Different relation types may have different traversal semantics

### Recommendation

**Implement scoping in two phases:**

**Phase 1 — Parent-child hierarchy scoping (addresses Developer1's critical need):**
- Add a `parent_artifact_id` scoping parameter to search that filters to descendants of the specified artifact using a recursive CTE on the artifact table.
- This is efficient, cycle-free (tree structure), and directly solves the "search within this project" use case.
- The parameter name should be `scope_artifact_id` or `ancestor_id` to clearly indicate hierarchical scoping.

**Phase 2 — General graph scoping (future):**
- Extend the existing `related_to` parameter with an optional `depth` parameter.
- Default depth is 1 (current behavior). Allow `depth=2`, `depth=3`, or `depth=recursive`.
- Implement cycle detection for general traversal.
- Consider a maximum depth limit to prevent runaway queries.

Developer1's recommendation of "option 3" (recursive depth in scoping) aligns with this phased approach. Phase 1 covers their critical use case; Phase 2 generalizes it.

### Performance Consideration

Recursive CTEs on parent-child hierarchies are well-optimized in PostgreSQL, especially when `parent_artifact_id` is indexed (which it is). For a typical Developer1 project with ~200 artifacts in a 3-level hierarchy, the recursive CTE will be fast.

General graph traversal through the relation table may require:
- Materialized path or closure table patterns for frequently-traversed hierarchies
- Query timeout limits for deep or wide traversals
- Result set size limits to prevent memory exhaustion

These are Phase 2 concerns and should not block Phase 1.

---

## 5. Pagination on All Ranking Types

### Developer1's Request

Currently only fulltext search supports `offset`-based pagination. Semantic, hybrid, and similar searches have `limit` but no `offset`.

### Analysis

This is a straightforward gap. The absence of pagination on vector-based search endpoints appears to be an implementation oversight rather than a design decision.

#### Concern: Offset Pagination on Vector Search

PostgreSQL's pgvector HNSW index does not natively support efficient offset-based pagination. A query with `LIMIT 10 OFFSET 100` must still compute the top 110 results and discard the first 100. For large result sets, this becomes expensive.

However, this is a known trade-off in vector search systems. The alternatives (keyset/cursor pagination) are difficult to apply to similarity-ranked results where there is no natural ordering key.

### Recommendation

**Accept this enhancement.** Add `offset` to all search endpoints (or to the unified search endpoint). Document the performance characteristics: offset pagination works well for small offsets but degrades for deep pagination. For consumers needing to page through many results, recommend using smaller result sets with more specific filtering rather than deep pagination.

---

## 6. Parent Expansion on Search Results

### Developer1's Request

Add an `include_parent` flag to search that returns the parent artifact alongside each matching child, eliminating the N+1 pattern of fetching parent files after chunk-level search.

### Analysis

Developer1 has already deprioritized this request and documented a client-side workaround using batch artifact retrieval (P0). The existing `GET /artifacts?ids=...` batch endpoint can fetch all needed parents in a single call after grouping search results by parent.

#### Concern: Response Size Explosion

Including full parent artifact content in search results would dramatically increase response payload sizes. If a search returns 10 chunks from 5 files, and each file is 50KB of source code, the response grows from ~5KB (chunks only) to ~255KB (chunks + parent file contents). This is a 50x increase per search call.

For API consumers making many searches (Developer1 reports ~550 HTTP calls per evaluation), this would significantly increase bandwidth consumption and parsing overhead — potentially worse than the N+1 pattern it aims to solve.

#### Alternative: The Batch Endpoint Already Solves This

The existing batch artifact retrieval endpoint (`GET /artifacts?ids=uuid1,uuid2,...`) allows fetching up to 100 artifacts in a single call. Developer1's N+1 pattern of "1 search + 8 parent lookups" becomes "1 search + 1 batch parent lookup" — 2 calls instead of 9.

### Recommendation

**Defer this enhancement.** The existing batch retrieval endpoint adequately addresses the N+1 problem. Document the recommended pattern:

1. Execute search to get matching chunks
2. Extract unique `parent_artifact_id` values from results
3. Batch-fetch all parent artifacts in a single call

This pattern is efficient, keeps response sizes manageable, and does not require API changes.

If future demand justifies it, consider a lighter-weight alternative: return `parent_artifact_id` and `parent_title` (but not `parent_content`) in search results. This gives consumers enough information to group and label results without the payload explosion.

---

## Cross-Cutting Concerns

### Backward Compatibility

The enhancement request contains a mix of additive changes and breaking changes:

| Enhancement | Breaking? | Notes |
|---|---|---|
| Artifact deletion | **Additive** | New endpoint, no existing behavior changes |
| Unified search | **Breaking** | Replaces four endpoints; requires deprecation strategy |
| Metadata filtering | **Additive** | New optional parameters on existing (or new) endpoints |
| Graph scoping | **Additive** | New optional parameters; extends existing `related_to` |
| Pagination | **Additive** | New optional parameter on existing endpoints |
| Parent expansion | N/A | Deferred |

Only the unified search endpoint represents a breaking change. All other enhancements can be implemented additively against the current API.

### Multi-Tenant Safety

All enhancements must respect Mimir's tenant isolation model. Specifically:

- **Deletion cascade** must not cross tenant boundaries. A cascade from a parent artifact must only affect children within the same tenant.
- **Graph scoping** must be tenant-scoped. Recursive traversal must include `AND tenant_id = %s` at every level.
- **Metadata filtering** queries must be scoped to the requesting tenant.

These are implementation constraints, not design decisions — but they are critical enough to document here.

### The Append-Only Invariant Is Preserved — and Scoped

Developer1's deletion request initially appeared to require relaxing the append-only invariant. The tenant-type-scoped policy approach resolves this tension: the invariant is preserved absolutely for tenant types that require it (`audited`/`project`), and appropriately relaxed for tenant types where operational agility matters more than auditability (`sandbox`/`experiment`).

This is not a compromise — it is a recognition that different data has different lifecycle requirements, and the tenant type is the correct place to express that policy.

---

## Recommended Priority and Sequencing

Based on the analysis above, here is the recommended implementation order:

### Phase 1: Critical Operational Gaps (Immediate)

**1a. Tenant-Type-Scoped Deletion with Cascade**
- Add `deletion_policy` column to `tenant_type` vocabulary table
- Add `deleted_at` column to artifact table
- Implement `DELETE /artifacts/{id}` with `?cascade=true`, behavior governed by tenant type policy
- Update all query paths to exclude soft-deleted artifacts
- *Unblocks Developer1 immediately; interim workaround: create a new sandbox tenant*

**1b. Parent-Child Hierarchy Scoping on Search**
- Add `scope_artifact_id` parameter to all existing search endpoints
- Implement recursive CTE on `parent_artifact_id` to filter candidates
- *Solves the cross-project contamination problem with minimal API change*

### Phase 2: Search Infrastructure (Near-term)

**2a. Metadata Filtering**
- Add `metadata_filters` parameter to all search endpoints
- Implement JSONB-based server-side filtering with AND/OR semantics
- *Enables correct pagination and eliminates client-side post-filtering*

**2b. Pagination on All Search Types**
- Add `offset` parameter to semantic, hybrid, and similar search
- Document performance characteristics for deep pagination

### Phase 3: Search Unification (Next Major Version)

**3a. Unified Search Endpoint**
- Implement `POST /search` with discriminated ranking strategy
- Deprecate individual search endpoints with transition period
- Incorporate all Phase 1 and Phase 2 features into the unified contract

**3b. General Graph Scoping**
- Extend scoping to support relation-type-based traversal with configurable depth
- Cycle detection and depth limits for general graph traversal

### What Is Not Recommended

- **System-wide deletion policy**: Deletion behavior must vary by tenant type, not be a single system setting.
- **Parent expansion on search results**: Defer; existing batch retrieval is adequate.
- **Immediate removal of the four search endpoints**: Use deprecation, not replacement.

---

## Summary of Positions

| Enhancement | Verdict | Rationale |
|---|---|---|
| Cascade artifact deletion | **Accept with modification** | Deletion policy scoped by tenant type: sandbox=physical, standard=soft, audited=forbidden |
| Unified search endpoint | **Accept as future direction** | Implement additively alongside existing endpoints; deprecate over time |
| Metadata filtering | **Accept** | High value, no architectural tension, leverages existing JSONB infrastructure |
| Graph scoping | **Accept in phases** | Phase 1: parent-child CTE (immediate). Phase 2: general relation traversal (future) |
| Pagination on all types | **Accept** | Straightforward gap closure |
| Parent expansion | **Defer** | Batch retrieval endpoint already solves the N+1 problem |

### Acknowledgment

Developer1's enhancement request is exceptionally well-documented. The clear articulation of real production problems, current workarounds, and proposed solutions — including the thoughtful distinction between scoping and graph traversal — reflects a mature integration consumer. The Mimir team should view this request as evidence that the system is being used seriously and that investment in these enhancements will directly benefit real workloads.

The unified search endpoint proposal in particular represents the kind of architectural insight that usually comes from within a team, not from an external consumer. The argument that "four endpoints sharing 80% of their parameters is a code smell" is correct, and the team should act on it — thoughtfully and with appropriate migration support.