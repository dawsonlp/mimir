# Soft-Delete Interaction Semantics

**Author**: Mimir Architecture Team  
**Date**: 2026-02-13  
**Status**: Specification — defines behavior before implementation  
**Phase**: 2 (Deletion Infrastructure)

---

## Overview

Soft deletion sets `deleted_at = now()` on an artifact row. The artifact remains in the database for audit and recovery purposes but is excluded from normal API interactions. This document specifies how soft-deleted artifacts interact with every system surface.

---

## 1. Scope Anchor Resolution

**Rule**: A `scope_artifact_id` pointing to a soft-deleted artifact returns **empty results**.

The scope anchor must be active (`deleted_at IS NULL`). If the anchor has been soft-deleted, the search returns an empty result set — not an error. This preserves the contract that scoping narrows results rather than failing.

**Rationale**: A deleted scope anchor means the conceptual container (e.g., a project or document) no longer exists from the user's perspective. Returning results from within a deleted container would violate user expectations.

---

## 2. Recursive CTE for Hierarchy Scoping

**Rule**: The recursive CTE excludes soft-deleted intermediate nodes.

When resolving descendants of a scope anchor via `parent_artifact_id`, the CTE includes `AND deleted_at IS NULL` at every recursion level. If a file artifact in the middle of the tree is soft-deleted, its child chunks become **unreachable via scoping** even if those children are not themselves soft-deleted.

```sql
WITH RECURSIVE descendants AS (
    SELECT id FROM mimirdata.artifact
    WHERE id = %s AND tenant_id = %s AND deleted_at IS NULL
    UNION ALL
    SELECT a.id FROM mimirdata.artifact a
    INNER JOIN descendants d ON a.parent_artifact_id = d.id
    WHERE a.tenant_id = %s AND a.deleted_at IS NULL
)
SELECT id FROM descendants
```

**Rationale**: Soft-deleting a parent logically removes its entire subtree from visibility. Children that should remain visible must be explicitly re-parented before the parent is deleted.

---

## 3. GET /artifacts/{id}

**Default behavior**: Returns **404 Not Found** for soft-deleted artifacts.

All retrieval queries include `AND deleted_at IS NULL`. From the API consumer's perspective, a soft-deleted artifact does not exist.

**Administrative access**: `GET /artifacts/{id}?include_deleted=true` returns the artifact even if soft-deleted, with the `deleted_at` timestamp visible in the response. This is for administrative and recovery workflows only.

---

## 4. GET /artifacts/{id}/children

**Rule**: Excludes soft-deleted children by default.

The children query includes `AND deleted_at IS NULL`. Only active children are returned. This is consistent with the general rule that soft-deleted artifacts are invisible to normal queries.

---

## 5. Embeddings and Semantic Search

**Rule**: Embeddings of soft-deleted artifacts do **NOT** participate in semantic/vector search.

All search queries that join `artifact` include `AND a.deleted_at IS NULL`. This ensures that vector similarity results never surface content from deleted artifacts.

**Note**: The embedding rows themselves are not modified during soft-delete. They remain in the `embedding` and `mimir_vectors.vec_{type}` tables. Only the join filter excludes them. This preserves the option to un-delete (restore) an artifact and immediately recover its search presence.

---

## 6. Relations

**Rule**: Relations where the source **OR** target artifact is soft-deleted are excluded from relation queries and search scoping.

When listing relations or using `related_to` search filtering, the query joins against the artifact table to verify both endpoints are active:

- `source_id → artifact.deleted_at IS NULL`
- `target_id → artifact.deleted_at IS NULL`

If either endpoint is soft-deleted, the relation is invisible.

**Note**: The relation rows themselves are not modified. Un-deleting both artifacts restores the relation's visibility.

---

## 7. Provenance Events

**Rule**: Provenance events referencing soft-deleted artifacts **remain visible**.

Provenance is the audit trail. Soft-deleting an artifact does not hide or modify its provenance history. The provenance service does NOT add `deleted_at` filtering.

Additionally, soft-delete and physical-delete operations themselves generate provenance events:
- `action: "soft_delete"` with metadata including `cascade_count` and `deleted_ids`
- `action: "physical_delete"` with metadata including deletion counts per table

---

## 8. Cascade Behavior

**Soft-delete cascade**: When an artifact is soft-deleted with `cascade=true` (default), all descendants via `parent_artifact_id` are also soft-deleted with the same `deleted_at` timestamp. This is implemented as a single UPDATE using a recursive CTE.

**Conflict on non-cascade**: When `cascade=false` is explicitly set and the artifact has active children, the API returns **409 Conflict** with a message indicating the artifact has active children that must be deleted first or cascade must be enabled.

---

## 9. Deletion Policy Enforcement

The deletion behavior is determined by the tenant's type deletion policy:

| Tenant Type   | Policy            | DELETE Behavior                        |
|---------------|-------------------|----------------------------------------|
| `environment` | `soft_delete`     | Sets `deleted_at`, preserves all rows  |
| `project`     | `no_delete`       | Returns **403 Forbidden**              |
| `experiment`  | `physical_delete` | Removes rows from all tables           |

The policy is looked up from `tenant_type.deletion_policy` via the tenant's `tenant_type` field.

---

## Summary of Query Filters

| Surface                          | Filter Added                                    |
|----------------------------------|------------------------------------------------|
| `GET /artifacts/{id}`            | `AND deleted_at IS NULL` (default)             |
| `GET /artifacts` (list)          | `AND deleted_at IS NULL`                       |
| `GET /artifacts/{id}/children`   | `AND deleted_at IS NULL`                       |
| Fulltext search                  | `AND deleted_at IS NULL`                       |
| Semantic search                  | `AND a.deleted_at IS NULL`                     |
| Hybrid search                    | (via fulltext + semantic)                      |
| Similar artifacts                | (via semantic search)                          |
| Scope CTE (recursive)           | `AND deleted_at IS NULL` at every level        |
| Relation queries                 | JOIN artifact to verify both endpoints active  |
| Embedding listing                | JOIN artifact for `deleted_at IS NULL`         |
| Context traversal                | Artifact fetches exclude soft-deleted          |
| Provenance queries               | **No filter** — audit trail preserved          |