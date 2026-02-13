# Response to Developer1 Enhancement Request

**From**: Mimir Architecture Team  
**Date**: 2026-02-13  
**Re**: Enhancement Request dated 2026-02-13  
**Full evaluation**: [docs/enhancement-request-evaluation.md](docs/enhancement-request-evaluation.md)

---

First: thank you. This is the most thorough enhancement request we've received. The clear documentation of real production problems, workarounds attempted, and the distinction between scoping and graph traversal in your search proposal — this is the kind of feedback that makes a project better. We've written a full design evaluation document (linked above) with architectural analysis and trade-offs for each request, but this response covers the decisions and what to expect.

---

## Decisions Made

### 1. Artifact Deletion — Accepted, with a twist you'll like

We're implementing `DELETE /artifacts/{id}?cascade=true`, but the behavior will be governed by **tenant type**, not applied uniformly.

Your request surfaced a real tension with our append-only invariant. Rather than relaxing it system-wide, we're scoping the policy to tenant types:

| Tenant Type | What DELETE does |
|---|---|
| `experiment` / `sandbox` | **Physical deletion** — rows removed from artifact, embeddings, relations, provenance. Gone. |
| `environment` / `standard` | **Soft deletion** — `deleted_at` timestamp set, data excluded from all queries but preserved for audit |
| `project` / `audited` | **403 Forbidden** — deletion not permitted, append-only invariant enforced absolutely |

This means the append-only guarantee holds where it matters (production, compliance), and is appropriately relaxed where operational agility matters more (development, experimentation).

**Your immediate unblock**: Before deletion ships, you can create a new tenant with type `experiment`, re-ingest your 132 correct files there, and search against it. The contaminated tenant with the 6,006 `.venv` artifacts stays isolated. Once deletion lands, you can purge that tenant or cascade-delete the bad project artifact.

**Cascade behavior**: `?cascade=true` recursively deletes (or soft-deletes) all descendants via the `parent_artifact_id` tree — exactly the "delete a project and everything under it" semantics you described.

### 2. Parent-Child Hierarchy Scoping on Search — Accepted, shipping with Phase 1

We're adding a `scope_artifact_id` parameter to all existing search endpoints. When provided, search results are restricted to descendants of the specified artifact using a recursive CTE on the `parent_artifact_id` column.

This directly solves your "search only within this project" use case. For your hierarchy (project → file → chunk), passing the project artifact's UUID as `scope_artifact_id` will restrict semantic search to only the chunks under that project's files. No relation table traversal needed — the `parent_artifact_id` tree is more efficient and cycle-free.

This ships on the existing endpoints (`/search/semantic`, `/search/fulltext`, `/search/hybrid`, `/search/similar/{id}`). You don't need to wait for the unified endpoint to get scoped search.

### 3. Metadata Filtering on Search — Accepted

Your proposed contract — AND across keys, OR within array values — is the right starting point. We'll implement `metadata_filters` on all search endpoints using PostgreSQL's JSONB operators against the existing GIN-indexed `metadata` column.

Your observation that server-side filtering is essential for correct pagination is correct and was a factor in prioritizing this.

**Documented scope limitations** (for now): no negation, no range queries, no nested metadata filtering. These can be added later if demand warrants.

### 4. Pagination on All Search Types — Accepted

Adding `offset` to semantic, hybrid, and similar search. This was an implementation gap, not a design decision. We'll document that deep pagination on vector search degrades performance (pgvector HNSW computes top-N+offset and discards) — prefer tighter filtering over deep paging.

---

## Decisions Accepted in Principle — Timeline Not Committed

### 5. Unified Search Endpoint (`POST /search`)

Your argument is correct. Four endpoints sharing 80% of their parameters is a code smell, and the Elasticsearch `_search` precedent validates the single-endpoint-with-discriminated-body pattern.

**What we're committing to**:
- We will implement `POST /search` as an additive endpoint alongside the existing four.
- The existing endpoints will be deprecated (with deprecation headers) but not removed during a transition period.
- The unified endpoint will incorporate all Phase 1 and Phase 2 features (scoping, metadata filtering, pagination) from day one.

**What we're not committing to yet**:
- A timeline. The unified endpoint is a Phase 3 item. Phases 1 and 2 ship the features you need on the existing endpoints first.
- The dispatch logic for ambiguous combinations (e.g., `query_vector` + `similar_to`). Your proposed strategy table is a good starting point, but we need to work through edge cases before locking the contract.
- Composite ranking modes like "similar + fulltext re-rank." These are interesting but need design work beyond what's in the initial request.

**Your validation that we preserve**: "Embedding generation is the client's job." Correct. The unified endpoint will accept `query_vector` (pre-computed), never `query_text`. Mimir stores and indexes vectors; generation is the client's concern.

### 6. General Graph Scoping with Depth Control

Your distinction between scoping (WHERE clause on candidates) and graph traversal (multi-hop query language) is architecturally sound and we're adopting it.

Phase 1 gives you parent-child hierarchy scoping via `scope_artifact_id` (recursive CTE). This covers your critical use case.

Phase 2 will extend the existing `related_to` parameter with a `depth` option for general relation-based traversal. This covers your secondary use cases (e.g., "all evaluations for this expectation" via `references` relations). Cycle detection and depth limits are Phase 2 concerns.

---

## Deferred

### Parent Expansion on Search Results

We're deferring this. You've already deprioritized it, and the existing batch retrieval endpoint (`GET /artifacts?ids=...`) reduces your N+1 pattern from "1 search + 8 parent lookups" to "1 search + 1 batch parent lookup" — 2 calls instead of 9.

**Recommended pattern** (works today):
1. Execute search → get matching chunks (each has `parent_artifact_id`)
2. Collect unique `parent_artifact_id` values from results
3. `GET /artifacts?ids=parent1,parent2,parent3,...` → all parents in one call

If future demand warrants, we may add lightweight parent metadata (ID + title, not content) to search results to help with grouping and display.

---

## Implementation Sequencing

| Phase | What Ships | Your Impact |
|---|---|---|
| **Phase 1** (immediate) | Tenant-type-scoped deletion with cascade; `scope_artifact_id` on all search endpoints | Unblocks cleanup and scoped search — your two critical requests |
| **Phase 2** (near-term) | Metadata filtering; pagination on all search types | Eliminates client-side post-filtering; enables proper paging |
| **Phase 3** (next major) | Unified `POST /search`; general graph scoping with depth | API consolidation; advanced graph queries |

### Your Immediate Action Items (Before Phase 1 Ships)

1. **Create a new tenant** with type `experiment` for your clean pipeline runs
2. **Re-ingest** the 132 correct project files into the new tenant
3. **Point your search** at the new tenant via `X-Tenant-ID`

This gives you an uncontaminated search space immediately. Once Phase 1 ships, you can cascade-delete the garbage from the old tenant or just abandon it.

---

## Questions for You

As we move into implementation, a few things we'd like your input on:

1. **Parameter naming**: For hierarchy scoping, do you prefer `scope_artifact_id`, `ancestor_id`, or `parent_artifact_id` (overloaded with the existing field name)? We're leaning toward `scope_artifact_id` to avoid confusion with the schema column.

2. **Deletion response format**: For cascade deletes, should the response include a count of affected artifacts/embeddings/relations? e.g., `{"deleted": {"artifacts": 134, "embeddings": 398, "relations": 267}}`. This adds implementation complexity but is useful for verification.

3. **Metadata filter contract**: Your AND/OR proposal is clean. Do you foresee needing negation (`NOT chunk_type = "header"`) in the near term, or is positive matching sufficient for your current workflows?

---

We're glad Mimir is being used seriously enough to generate requests like this. The contaminated-data problem and the unified search proposal in particular have made the system better for every future consumer. Keep them coming.

— Mimir Architecture Team