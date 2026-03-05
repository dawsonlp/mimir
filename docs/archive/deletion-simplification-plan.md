# Deletion Simplification — Development Plan

**Author**: Mimir Architecture Team  
**Date**: 2026-02-20  
**Status**: Approved  
**Scope**: Remove artifact-level deletion infrastructure; add tenant-level deletion

---

## Decision

Artifact-level deletion (soft-delete and physical-delete) is removed from Mimir. The system returns to its original append-only invariant for all content tables.

**Rationale**: The failure modes of artifact deletion (cascade semantics, orphaned relations, query filter proliferation, soft-delete visibility rules) create cross-cutting complexity that touches every read path. The recommended data cleanup workflow — export the desired subgraph, import to a new tenant, delete the old tenant — achieves the same goal with dramatically less system complexity.

**Cleanup mechanism**: Tenant deletion via FK CASCADE. All content tables already have `ON DELETE CASCADE` foreign keys to the tenant table. Dropping a tenant atomically removes all its artifacts, relations, embeddings, vectors, and provenance events.

**Policy model**: Policies are defined at the tenant type level. The current policy for all tenant types is **append-only** (no artifact-level deletion). Future tenant types may introduce different policies if the need arises, but the policy infrastructure will be added at that point — not speculatively.

---

## Scope of Changes

### Phase A: Remove Artifact Deletion Infrastructure

#### A1. Migration Consolidation (Schema)

Since the system does fresh database builds (no incremental migration from existing data), consolidate migrations:

- **Remove migration 006** (`deletion_infrastructure`) entirely — both `.up.sql` and `.down.sql`
- **Edit migration 002** (artifact): Ensure no `deleted_at TIMESTAMPTZ NULL` column or `idx_artifact_deleted` partial index exists (these were added by 006)
- **Edit migration 001** (tenant): Ensure no `deletion_policy` column on `tenant_type` table (added by 006)
- **Edit migration 007** (AGE graph projection): Remove `age_artifact_soft_delete_vertex` trigger and `trg_artifact_soft_delete_vertex()` function — these exist solely to handle soft-delete events
- **Renumber**: Current migration 007 becomes 006

**Result**: Clean migration set (001–006) with no deletion concepts.

#### A2. Artifact Service (`artifact_service.py`)

- Remove `soft_delete_artifact()` function (~50 lines)
- Remove `physical_delete_artifact()` function (~100 lines)
- Remove `include_deleted` parameter from: `get_artifact`, `list_artifacts`, `_get_artifacts_by_ids`, `get_children`
- Remove all `deleted_at IS NULL` / `deleted_at` filter logic from every query
- Remove `SoftDeleteResponse` and `PhysicalDeleteResponse` imports
- Update `_ARTIFACT_COLUMNS` to remove `deleted_at` (15 columns, not 16)
- Update `_row_to_artifact_response` mapping (15 columns, not 16)

#### A3. Artifact Router (`routers/artifacts.py`)

- Remove `DELETE /artifacts/{id}` endpoint entirely
- Remove `include_deleted` query parameter from `get_artifact` and `get_artifact_children`
- Remove imports: `SoftDeleteResponse`, `PhysicalDeleteResponse`, `tenant_service`

#### A4. Artifact Schemas (`schemas/artifact.py`)

- Remove `SoftDeleteResponse` class
- Remove `PhysicalDeleteResponse` class
- Remove `deleted_at` field from `ArtifactResponse`

#### A5. Tenant Service (`tenant_service.py`)

- Remove `get_deletion_policy()` function
- Remove `deletion_policy` from `_TENANT_SELECT` JOIN — no longer need to join `tenant_type` for this column
- Update `_row_to_tenant_response` to 8 columns (remove `deletion_policy`)

**Note**: The `tenant_type` JOIN is removed since `deletion_policy` was its only purpose. If future tenant-type-level fields are needed, the JOIN can be re-added at that time.

#### A6. Tenant Schema (`schemas/tenant.py`)

- Remove `deletion_policy` field from `TenantResponse`

#### A7. Relation Service (`relation_service.py`)

- `get_relation`: Remove JOIN to artifact table (both `src` and `tgt`). Query becomes simple single-table lookup.
- `list_relations`: Remove double artifact JOIN. Query becomes single-table with optional filters.
- `get_artifact_relations`: Remove double artifact JOIN. Query becomes single-table.
- Remove all `src.deleted_at IS NULL AND tgt.deleted_at IS NULL` conditions.

**This is the biggest performance win** — eliminates 2 index lookups per relation row on every relation read.

#### A8. Search Service (`search_service.py`)

- `fulltext_search`: Remove `AND deleted_at IS NULL` from WHERE clause
- `semantic_search`: Remove `AND a.deleted_at IS NULL` from JOIN WHERE clause
- `_resolve_scope_descendants`: Remove `AND deleted_at IS NULL` from anchor check and recursive CTE (3 places)

#### A9. Context Service (`context_service.py`)

- Remove soft-delete exclusion filters from relation traversal JOINs (same pattern as relation_service)

#### A10. Tests

- Delete `tests/integration/test_deletion_phase2.py` entirely (~350 lines)
- Audit remaining tests for any `include_deleted` usage or `deleted_at` assertions — remove them

#### A11. Documentation

- Archive or remove `docs/soft-delete-semantics.md`
- Update `docs/enhancement-roadmap-checklist.md`: Mark Phase 2 items as "Removed — replaced by tenant-level deletion"
- Update `docs/data-model.md`: Remove any `deleted_at` column references, reinforce append-only invariant
- Update `docs/entity-guide.md` if it references deletion behavior
- Update API version notes

---

### Phase B: Add Tenant Deletion

#### B1. Tenant Service Addition

Add `delete_tenant()` function to `tenant_service.py`:

1. Call `mimirdata.drop_tenant_graph(tenant_id)` to remove the AGE graph
2. `DELETE FROM mimirdata.tenant WHERE id = %s` — FK CASCADE handles all content tables
3. Return success/not-found

~15 lines of implementation.

**FK CASCADE chain** (already defined in existing migrations):

```
tenant (id)
├── artifact.tenant_id        → ON DELETE CASCADE
│   ├── relation.source_id    → ON DELETE CASCADE
│   ├── relation.target_id    → ON DELETE CASCADE
│   ├── embedding.artifact_id → ON DELETE CASCADE
│   │   └── vec_{type}.embedding_id → ON DELETE CASCADE
│   └── (parent_artifact_id   → ON DELETE SET NULL — self-ref, harmless)
├── relation.tenant_id        → ON DELETE CASCADE
├── embedding.tenant_id       → ON DELETE CASCADE
└── provenance_event.tenant_id → ON DELETE CASCADE
```

#### B2. Tenant Router Addition

Add `DELETE /tenants/{tenant_id}` endpoint to `routers/tenants.py`:

- Returns 204 No Content on success
- Returns 404 if tenant not found
- Safety: Consider requiring confirmation header (e.g., `X-Confirm-Delete: true`) as a guard against accidental deletion

~15 lines of implementation.

#### B3. Tenant Deletion Tests

Add integration tests:

- Delete tenant with data (artifacts, relations, embeddings) — verify all gone
- Delete tenant — verify AGE graph is dropped
- Delete nonexistent tenant — 404
- Verify other tenants' data is unaffected (isolation)

---

### Phase C: Cleanup and Verification

#### C1. Full Test Suite Run

- Run complete test suite to verify no regressions
- `grep -r "deleted_at\|include_deleted\|deletion_policy\|soft_delete\|physical_delete" backend/src/` — verify zero matches
- `grep -r "SoftDeleteResponse\|PhysicalDeleteResponse" backend/src/` — verify zero matches

#### C2. Changelog Entry

- Document the architectural simplification with rationale
- Version bump consideration

---

## File Impact Summary

| File | Action | Lines Affected (est.) |
|------|--------|----------------------|
| `migrations/versions/006_deletion_infrastructure.up.sql` | Delete | -40 |
| `migrations/versions/006_deletion_infrastructure.down.sql` | Delete | -15 |
| `migrations/versions/007→006_age_graph_projection.up.sql` | Edit: remove soft-delete trigger | -30 |
| `migrations/versions/007→006_age_graph_projection.down.sql` | Edit: remove soft-delete trigger drop | -3 |
| `services/artifact_service.py` | Remove ~200 lines of deletion code | -200 |
| `routers/artifacts.py` | Remove DELETE endpoint + include_deleted | -50 |
| `schemas/artifact.py` | Remove 2 response classes + 1 field | -20 |
| `services/tenant_service.py` | Remove get_deletion_policy, simplify queries, add delete_tenant | Net -10 |
| `routers/tenants.py` | Add DELETE endpoint | +15 |
| `schemas/tenant.py` | Remove deletion_policy field | -2 |
| `services/relation_service.py` | Simplify 3 queries (remove double JOINs) | -30 |
| `services/search_service.py` | Remove 5 filter clauses | -10 |
| `services/context_service.py` | Remove soft-delete filters | -5 |
| `tests/integration/test_deletion_phase2.py` | Delete entirely | -350 |
| `docs/soft-delete-semantics.md` | Archive/delete | -100 |
| **Net** | | **~-850 lines removed, ~30 added** |

---

## Ordering

Execute phases in order: **A → B → C**. Phase A removes the old infrastructure, Phase B adds the new (simpler) mechanism, Phase C verifies the result.

Within Phase A, the order is flexible since this is a fresh-build system, but the logical sequence is: schema first (A1), then services (A2, A5, A7, A8, A9), then routers (A3), then schemas (A4, A6), then tests (A10), then docs (A11).