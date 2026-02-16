# AGE Graph Projection — Technical Design

**Status**: Approved  
**Date**: 2025-02-14  
**Author**: Senior Engineer  
**Implements**: `docs/graph-search-design.md` §7 (Graph Projection)  
**Migration**: 007

---

## 1. Context

Mímir v3.0.0 stores knowledge as artifacts connected by relations in PostgreSQL. The `postgres-batteries-inc:18` image now includes Apache AGE 1.7.0, enabling native Cypher graph queries. This document defines how relational data is projected into AGE graphs and kept in sync.

### Design Decisions (from architecture review)

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Vertex modeling | Generic `Artifact` label with `type` property | Types are data (vocabulary tables), not schema |
| Edge modeling | Generic `Relation` label with `type` property | Multi-hop traversal queries stay simple |
| Sync strategy | Triggers + bulk rebuild function | Relation table stays sole source of truth |
| Tenant isolation | Separate graph per tenant | Hard isolation, cleaner Cypher queries |

---

## 2. Graph Naming Convention

Each tenant gets its own AGE graph:

```
mimir_tenant_{tenant_id}
```

Where `tenant_id` is the integer primary key from `mimirdata.tenant`. Examples:
- Tenant 1 → `mimir_tenant_1`
- Tenant 42 → `mimir_tenant_42`

This uses the tenant's stable integer ID, not the mutable shortname.

---

## 3. Graph Data Model

### 3.1 Vertex: `Artifact`

Properties stored on vertices (enough for filtering and identification during traversal):

| Property | Type | Source |
|----------|------|--------|
| `mimir_id` | text | `artifact.id::text` (UUID as string) |
| `artifact_type` | text | `artifact.artifact_type` |
| `title` | text | `artifact.title` (nullable) |
| `created_at` | text | `artifact.created_at::text` |

**Not stored**: `content`, `content_hash`, `metadata`, `source_uri`, embeddings. These are retrieved from relational tables after graph traversal identifies the relevant artifact IDs.

### 3.2 Edge: `Relation`

Properties stored on edges:

| Property | Type | Source |
|----------|------|--------|
| `mimir_id` | text | `relation.id::text` (UUID as string) |
| `relation_type` | text | `relation.relation_type` |
| `confidence` | float | `relation.confidence` (nullable) |
| `created_at` | text | `relation.created_at::text` |

### 3.3 Design Principle

The graph is a **traversal index**, not a data store. It answers "which artifacts are connected and how?" — then the relational tables provide the full artifact data. This avoids data duplication and keeps the relational tables as the single source of truth.

---

## 4. Sync Architecture

### 4.1 Overview

```
┌──────────────────────┐
│  Application Layer    │  (no changes)
│  artifact_service.py  │
│  relation_service.py  │
│  tenant_service.py    │
└──────────┬───────────┘
           │ INSERT/UPDATE/DELETE
           ▼
┌──────────────────────┐
│  Relational Tables    │  (source of truth)
│  mimirdata.artifact   │
│  mimirdata.relation   │
│  mimirdata.tenant     │
└──────────┬───────────┘
           │ PostgreSQL Triggers
           ▼
┌──────────────────────┐
│  AGE Graphs           │  (derived view)
│  mimir_tenant_{id}    │
│  Artifact vertices    │
│  Relation edges       │
└──────────────────────┘
```

### 4.2 Trigger Matrix

| Table | Event | Trigger Function | Action |
|-------|-------|-----------------|--------|
| `tenant` | AFTER INSERT | `trg_tenant_create_graph()` | Create graph `mimir_tenant_{id}` with labels |
| `artifact` | AFTER INSERT | `trg_artifact_create_vertex()` | Create `Artifact` vertex in tenant's graph |
| `artifact` | AFTER UPDATE OF `deleted_at` | `trg_artifact_soft_delete_vertex()` | If `deleted_at` set: remove vertex (AGE cascades edge removal) |
| `artifact` | AFTER DELETE | `trg_artifact_delete_vertex()` | Remove vertex on physical delete |
| `relation` | AFTER INSERT | `trg_relation_create_edge()` | Create `Relation` edge between two vertices |
| `relation` | AFTER DELETE | `trg_relation_delete_edge()` | Remove edge on physical delete |

### 4.3 Trigger Execution Context

- AGE is loaded via `shared_preload_libraries` in the postgres-batteries-inc image
- All Cypher calls use `ag_catalog.cypher(graph_name, query, params)` — fully qualified, no search_path manipulation
- Triggers execute in the same transaction as the originating INSERT/UPDATE/DELETE
- Trigger failure rolls back the entire operation (fail-fast principle)

### 4.4 Bulk Rebuild Function

`mimirdata.rebuild_tenant_graph(p_tenant_id INT)`:

1. Drop existing graph if it exists
2. Create fresh graph with `Artifact` and `Relation` labels
3. INSERT all non-deleted artifacts as vertices
4. INSERT all relations (where both source and target are non-deleted) as edges

Use cases:
- Migration bootstrap (initial data projection)
- Disaster recovery (graph corruption)
- Manual repair after schema changes

---

## 5. AGE/Cypher Patterns

### 5.1 Create Vertex

```sql
SELECT * FROM ag_catalog.cypher('mimir_tenant_1', $$
    CREATE (:Artifact {
        mimir_id: $mimir_id,
        artifact_type: $artifact_type,
        title: $title,
        created_at: $created_at
    })
$$, '{"mimir_id": "uuid-str", "artifact_type": "document", "title": "My Doc", "created_at": "2025-01-01T00:00:00Z"}'::agtype) AS (v agtype);
```

### 5.2 Create Edge

```sql
SELECT * FROM ag_catalog.cypher('mimir_tenant_1', $$
    MATCH (s:Artifact {mimir_id: $source_id}), (t:Artifact {mimir_id: $target_id})
    CREATE (s)-[:Relation {
        mimir_id: $mimir_id,
        relation_type: $relation_type,
        confidence: $confidence,
        created_at: $created_at
    }]->(t)
$$, '{"source_id": "...", "target_id": "...", ...}'::agtype) AS (e agtype);
```

### 5.3 Delete Vertex (cascades edges)

```sql
SELECT * FROM ag_catalog.cypher('mimir_tenant_1', $$
    MATCH (a:Artifact {mimir_id: $mimir_id})
    DETACH DELETE a
$$, '{"mimir_id": "uuid-str"}'::agtype) AS (v agtype);
```

### 5.4 Multi-hop Traversal (future query example)

```sql
SELECT * FROM ag_catalog.cypher('mimir_tenant_1', $$
    MATCH path = (start:Artifact {mimir_id: $start_id})-[:Relation*1..5]->(end:Artifact)
    RETURN path
$$, '{"start_id": "uuid-str"}'::agtype) AS (path agtype);
```

---

## 6. Migration 007 Structure

```sql
-- Phase 1: Helper functions
--   create_tenant_graph(tenant_id)
--   drop_tenant_graph(tenant_id)
--   rebuild_tenant_graph(tenant_id)

-- Phase 2: Trigger functions
--   trg_tenant_create_graph()
--   trg_artifact_create_vertex()
--   trg_artifact_soft_delete_vertex()
--   trg_artifact_delete_vertex()
--   trg_relation_create_edge()
--   trg_relation_delete_edge()

-- Phase 3: Attach triggers to tables

-- Phase 4: Bootstrap existing data
--   Loop through existing tenants → rebuild_tenant_graph()
```

### Down Migration

Reverse order:
1. Drop all triggers
2. Drop all trigger functions
3. Drop all tenant graphs (loop through existing tenants)
4. Drop all helper functions

No relational data is affected by the down migration.

---

## 7. Constraints and Limitations

| Constraint | Impact | Mitigation |
|-----------|--------|------------|
| AGE Cypher in triggers requires `ag_catalog` in search_path or fully qualified calls | Use fully qualified `ag_catalog.cypher()` everywhere | Standard pattern |
| AGE vertex deletion cascades edges automatically | Expected behavior — matches soft-delete semantics | None needed |
| Graph operations add latency to INSERT triggers | Minimal — single Cypher operation per INSERT | Monitor; if problematic, move to async |
| AGE 1.7.0 is relatively new | Test thoroughly | Bulk rebuild provides recovery path |
| Tenant deletion should drop graph | Handled by trigger or manual cleanup | Add tenant DELETE trigger |

---

## 8. Testing Strategy

| Test | Type | Verifies |
|------|------|----------|
| Fresh migration applies cleanly | Integration | Migration SQL is valid |
| Tenant create → graph exists | Integration | Tenant trigger works |
| Artifact insert → vertex exists | Integration | Artifact trigger works |
| Relation insert → edge exists | Integration | Relation trigger works |
| Soft-delete → vertex removed | Integration | Soft-delete trigger works |
| Physical delete → vertex removed | Integration | Delete trigger works |
| Rebuild function → matches relational data | Integration | Bulk rebuild correctness |
| Relation with deleted source → no edge | Integration | Edge consistency |

All tests use `psql` or the existing test infrastructure against a live postgres container.

---

## 9. What This Does NOT Cover

- Cypher query API endpoints (future — graph-search-design.md §8)
- Search orchestrator integration (future — graph-search-design.md §4)
- Graph traversal engine service layer (future)
- Performance tuning / indexing on graph properties (future, when query patterns are known)

This migration establishes the **data foundation**. Query capabilities are built on top of it.