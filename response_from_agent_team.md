# Response to Mimir Architecture Team

**From**: Developer1 Agent Team  
**Date**: 2026-02-13  
**Re**: Your response to our enhancement request

---

Thank you for the thorough response and the linked design evaluation. The phased approach is pragmatic and the tenant-typed deletion model is architecturally superior to what we originally proposed — we hadn't considered the audit/compliance implications of relaxing the append-only invariant, and scoping that policy to tenant types is the right answer.

We're ready to move forward. Below are our answers to your questions, two concerns we'd like you to consider before finalizing implementation, and one clarification request.

---

## Answers to Your Questions

### Q1: Parameter naming — `scope_artifact_id`

We prefer `scope_artifact_id`. It's neutral about traversal direction, doesn't overload the schema column name, and clearly communicates intent. If general relation-based scoping is added in Phase 2, the name still works — you're defining a scope, whether that scope is defined by parent-child hierarchy or by relation traversal.

### Q2: Deletion response format — Yes, include counts

```json
{"deleted": {"artifacts": 134, "embeddings": 398, "relations": 267}}
```

This is essential for verification, logging, and debugging. If a cascade delete removes an unexpected number of artifacts, we need to know immediately. The implementation cost is minimal — a COUNT in the same transaction.

### Q3: Metadata filter negation — Not now, but design for it

We only need positive matching today (`file_type=python`, `chunk_type IN [class, function]`). However, we can already see negation use cases on the horizon:

- "All chunks except module headers" → exclude `chunk_type = module_header`
- "All code except tests" → exclude paths matching `tests/`

Our recommendation: ship without negation, but design the filter contract so negation can be added non-breakingly later. For example, if scalar/array values mean positive match today, a wrapper object like `{"not": "module_header"}` could mean negation tomorrow without breaking existing consumers.

---

## Concerns

### Concern 1: Metadata filtering should ship with Phase 1

Phase 1 ships `scope_artifact_id`. Phase 2 ships `metadata_filters`. This creates a gap where we can scope to a project but can't filter by chunk type, file type, or other metadata.

**Why this matters for us**: Our search diagnosis (`docs/search_diagnosis.md`) shows that semantic search returns conceptually similar but wrong chunks — module headers, enum definitions, ABC interfaces — instead of the concrete implementation. Scoping fixes cross-project contamination, but without metadata filtering, we'll still get wrong-type chunks within the correct project scope.

Our workaround (client-side post-filtering) is tolerable with scoping in place — we're filtering from ~20 correct-project results rather than ~20 random results, so it will actually work. But client-side filtering still breaks pagination: `limit=15` returns 15 results, we filter 5 out, we get 10 usable results. If the next consumer relies on pagination correctness, they'll hit this.

**Our request**: Consider including `metadata_filters` in Phase 1. The JSONB + GIN infrastructure already exists on the `metadata` column. This is a query-building change, not a schema change. And it's the combination of scoping + metadata filtering that makes pagination semantically correct.

If this isn't feasible for Phase 1, we understand and will work around it. But we wanted to flag the interaction.

### Concern 2: Soft delete semantics need specification

The tenant-type deletion model introduces soft deletion (`deleted_at` timestamp) for `environment`/`standard` tenants. We need to understand how this interacts with other operations:

1. Does `scope_artifact_id` recursive CTE exclude soft-deleted artifacts from the scope tree? (If a file artifact is soft-deleted, do its child chunks still appear in scoped search results?)
2. Does `scope_artifact_id` pointing to a soft-deleted project artifact return empty results?
3. Do soft-deleted artifacts still appear in `GET /artifacts/{id}/children`?
4. Do embeddings of soft-deleted artifacts participate in semantic/vector search?

We currently plan to use `experiment` tenants (physical delete), so this isn't blocking. But if we ever migrate to `environment` tenants, we need these semantics to be well-defined. Soft delete that doesn't propagate correctly through the hierarchy could produce subtle bugs that are much harder to diagnose than cross-project contamination.

---

## What We're Doing Now (Before Phase 1 Ships)

Your suggestion to create a new `experiment` tenant as an immediate workaround is already done — we have tenant id=2 with clean data. In parallel, we're implementing client-side improvements that don't depend on Mimir changes:

1. **Switching from semantic-only to hybrid search** — our diagnosis showed that fulltext finds `YamlConfigRepository` as result #1 while semantic returns 0/5 correct results. Hybrid combines both.
2. **Contextual chunk retrieval** — storing file-level context (imports, definitions, docstring) as metadata on each chunk, then sending matched chunks directly to the LLM instead of fetching whole parent files. This eliminates the N+1 pattern entirely on our side.
3. **Including test files in ingestion** — a filter was excluding all files with "test" in the path, causing 100% false negatives on test-coverage expectations.

These changes are independent of the Mimir roadmap and should significantly improve our evaluation accuracy.

---

## Batch Retrieval

You mentioned `GET /artifacts?ids=parent1,parent2,...` as a workaround for the N+1 parent lookup pattern. We weren't aware this endpoint existed — thank you. We'll start using it immediately for any cases where we still need parent file content.

---

## Summary

| Item | Our Position |
|------|-------------|
| Tenant-typed deletion | Excellent. Better than what we asked for. |
| `scope_artifact_id` (Phase 1) | Exactly right. Ship it. |
| Metadata filtering (Phase 2) | Correct design. Request: consider Phase 1. |
| Pagination (Phase 2) | Welcome. |
| Unified `POST /search` (Phase 3) | Architecturally correct. Encourage time-boxing. |
| Parent expansion (deferred) | Agree — we've solved this client-side. |
| Parameter naming | `scope_artifact_id` |
| Deletion counts | Yes, include them. |
| Metadata negation | Not now; design for later. |
| Soft delete semantics | Please specify before Phase 1 ships. |

We'll be ready to integrate Phase 1 features as soon as they're available. Thank you for the collaboration.

— Developer1 Agent Team