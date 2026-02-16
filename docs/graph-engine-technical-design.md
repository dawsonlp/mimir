# Graph Traversal Engine — Technical Design

**Status**: Approved  
**Date**: 2026-02-15  
**Author**: Lead Architect  
**Audience**: Lead Senior Engineer (implementer)  
**Implements**: `docs/graph-search-design.md` §4, §5.1, §4.3  
**Depends on**: `docs/age-graph-projection-technical-design.md` (Migration 007 — complete)  
**Release target**: v4.0.0

---

## 1. Objective

Build the Graph Traversal Engine — a new internal service that executes multi-hop graph queries against per-tenant AGE graphs using Cypher. This engine becomes the single point of graph traversal for Mimir, replacing the Python-side BFS in the context service and enabling graph-scoped search in a later phase.

This document covers **Phase 1** (engine + context migration) and **Phase 2** (graph-scoped search API). The engineer makes all implementation decisions within the constraints below.

---

## 2. Context: What Already Exists

### 2.1 AGE Graph Structure (Migration 007)

Each tenant has a named AGE graph: `mimir_tenant_{tenant_id}`

**Vertices** — label `Artifact`:
```
mimir_id: text       — artifact UUID
artifact_type: text  — e.g., "document", "decision", "chunk"
title: text          — display title
created_at: text     — ISO timestamp
```

**Edges** — label `Relation`:
```
mimir_id: text       — relation UUID
relation_type: text  — e.g., "derived_from", "supports", "parent_of"
confidence: float    — 0.0-1.0
created_at: text     — ISO timestamp
```

Six triggers keep the graph in sync with relational tables. The graph is a projection — relational tables are the source of truth.

### 2.2 AGE Query Pattern (Proven)

Migration 007's trigger functions execute Cypher via:
```sql
SELECT * FROM ag_catalog.cypher('mimir_tenant_1', $$
    MATCH (a:Artifact {mimir_id: '...'})
    RETURN a
$$) AS (v ag_catalog.agtype);
```

This pattern works with psycopg v3 async. The connection pool's `_configure_connection` callback already runs `LOAD 'age'` and sets `search_path = ag_catalog, mimirdata, public` on every connection.

### 2.3 Context Service (To Be Refactored)

`context_service._traverse_graph()` performs Python-side BFS:
- Iterative loop with a queue
- One SQL query per hop (N+1 queries for depth N)
- Python-side visited set for cycle detection
- Filters by relation_type and direction per hop

This will delegate to the new graph engine. The context service's external interface does not change.

---

## 3. Component Boundaries

```
┌─────────────────────────────┐     ┌────────────────────────┐
│     Search Orchestrator      │     │    Context Service      │
│  (routers/search.py — P2)   │     │ (services/context_svc) │
└──────────┬──────────────────┘     └──────────┬─────────────┘
           │                                    │
           │  graph_engine.traverse()           │  graph_engine.traverse()
           │  graph_engine.find_paths()         │
           ▼                                    ▼
┌──────────────────────────────────────────────────────────────┐
│                    Graph Traversal Engine                      │
│                  services/graph_engine.py                      │
│                                                                │
│  traverse(tenant_id, start_ids, relation_types, ...)          │
│  find_paths(tenant_id, from_id, to_id, ...)                  │
│                                                                │
│  Internal: builds Cypher → executes via ag_catalog.cypher()   │
└──────────────────────────────────────────────────────────────┘
           │
           │  SQL: SELECT * FROM ag_catalog.cypher(...)
           ▼
┌──────────────────────────────────────────────────────────────┐
│                 PostgreSQL + Apache AGE                        │
│            mimir_tenant_{id} graphs                           │
└──────────────────────────────────────────────────────────────┘
```

The graph engine:
- **Does**: Execute Cypher queries, enforce depth/size limits, return artifact ID sets and paths
- **Does not**: Hydrate artifacts (callers do that), perform text/semantic search, manage transactions (callers own the connection lifecycle)

---

## 4. Interfaces

### 4.1 Traverse

```python
@dataclass
class TraversalResult:
    artifact_ids: list[UUID]
    depth_map: dict[UUID, int]  # artifact_id → shortest distance from any start node

async def traverse(
    tenant_id: int,
    start_artifact_ids: list[UUID],
    relation_types: list[str] | None = None,
    direction: str = "both",           # "outgoing", "incoming", "both"
    max_depth: int = 3,
    include_start: bool = False,
) -> TraversalResult
```

**Constraints**:
- `max_depth` must be ≥ 1 and ≤ `GRAPH_MAX_DEPTH` (config, default 20)
- If result exceeds `GRAPH_MAX_RESULT_SET` (config, default 10,000), raise `GraphScopeTooLargeError`
- Query timeout: `GRAPH_QUERY_TIMEOUT_SECONDS` (config, default 5)

**Direction semantics**:
- `"outgoing"`: follow edges in stored direction (source→target)
- `"incoming"`: follow edges in reverse (target→source)
- `"both"`: follow edges in either direction

### 4.2 FindPaths

```python
@dataclass
class PathStep:
    artifact_id: UUID
    relation_type: str
    direction: str  # "outgoing" or "incoming" relative to traversal

@dataclass
class PathResult:
    paths: list[list[PathStep]]  # ordered shortest-first

async def find_paths(
    tenant_id: int,
    from_artifact_id: UUID,
    to_artifact_id: UUID,
    relation_types: list[str] | None = None,
    max_depth: int = 5,
) -> PathResult
```

Same constraints as Traverse for depth and timeout.

---

## 5. AGE Cypher Patterns

### 5.1 Pre-Implementation Spike (REQUIRED FIRST STEP)

Before writing the engine, validate these Cypher patterns against the running AGE 1.7.0 instance. Create `scripts/age_cypher_spike.py` that tests each pattern and documents results.

**Test 1 — Variable-length path (outgoing)**:
```sql
SELECT * FROM ag_catalog.cypher('mimir_tenant_1', $$
    MATCH (start:Artifact)-[:Relation*1..3]->(reached:Artifact)
    WHERE start.mimir_id = 'uuid-here'
    RETURN DISTINCT reached.mimir_id, 1
$$) AS (mimir_id ag_catalog.agtype, depth ag_catalog.agtype);
```

**Test 2 — Variable-length path (undirected / both)**:
```sql
SELECT * FROM ag_catalog.cypher('mimir_tenant_1', $$
    MATCH (start:Artifact)-[:Relation*1..3]-(reached:Artifact)
    WHERE start.mimir_id = 'uuid-here'
    RETURN DISTINCT reached.mimir_id
$$) AS (mimir_id ag_catalog.agtype);
```

**Test 3 — Relation type filtering in variable-length paths**:
AGE may not support `ALL(r IN relationships(path) WHERE ...)`. Test alternatives:
```sql
-- Option A: WHERE on edge property (may not work with variable-length)
SELECT * FROM ag_catalog.cypher('mimir_tenant_1', $$
    MATCH path = (start:Artifact)-[r:Relation*1..3]->(reached:Artifact)
    WHERE start.mimir_id = 'uuid-here'
    RETURN reached.mimir_id, length(path)
$$) AS (mimir_id ag_catalog.agtype, depth ag_catalog.agtype);
```

If relation type filtering in variable-length paths is not supported, the fallback is iterative single-hop Cypher (depth 1 per query, iterate in Python — similar to current BFS but with Cypher instead of SQL).

**Test 4 — shortestPath()**:
```sql
SELECT * FROM ag_catalog.cypher('mimir_tenant_1', $$
    MATCH p = shortestPath((a:Artifact)-[:Relation*..5]-(b:Artifact))
    WHERE a.mimir_id = 'uuid-a' AND b.mimir_id = 'uuid-b'
    RETURN p
$$) AS (path ag_catalog.agtype);
```

**Test 5 — length() function**:
```sql
SELECT * FROM ag_catalog.cypher('mimir_tenant_1', $$
    MATCH path = (start:Artifact)-[:Relation*1..5]->(reached:Artifact)
    WHERE start.mimir_id = 'uuid-here'
    RETURN reached.mimir_id, length(path) AS depth
$$) AS (mimir_id ag_catalog.agtype, depth ag_catalog.agtype);
```

**Test 6 — Result count / LIMIT**:
```sql
SELECT * FROM ag_catalog.cypher('mimir_tenant_1', $$
    MATCH (start:Artifact)-[:Relation*1..10]->(reached:Artifact)
    WHERE start.mimir_id = 'uuid-here'
    RETURN DISTINCT reached.mimir_id
    LIMIT 10001
$$) AS (mimir_id ag_catalog.agtype);
```

**Test 7 — agtype parsing**: Verify how `agtype` values are returned to psycopg. Are they strings? JSON? Do UUIDs come back quoted? This determines the parsing logic in the engine.

**Spike deliverable**: A markdown file (`docs/age-cypher-spike-results.md`) documenting what works, what doesn't, and the chosen approach for each pattern. This must be reviewed before proceeding to implementation.

---

## 6. Configuration

Add to `config.py` `Settings` class:

```python
# Graph engine settings
graph_max_depth: int = Field(default=20, ge=1, le=50, description="Maximum traversal depth ceiling")
graph_max_result_set: int = Field(default=10_000, ge=100, description="Maximum artifact IDs from a single traversal")
graph_query_timeout_seconds: int = Field(default=5, ge=1, le=30, description="Timeout for individual graph queries")
```

Environment variables: `GRAPH_MAX_DEPTH`, `GRAPH_MAX_RESULT_SET`, `GRAPH_QUERY_TIMEOUT_SECONDS`.

---

## 7. Error Handling

| Error | HTTP Code | When |
|-------|-----------|------|
| `GraphScopeTooLargeError` | 422 | Traversal returns > `graph_max_result_set` artifacts |
| `GraphQueryTimeoutError` | 504 | Cypher query exceeds `graph_query_timeout_seconds` |
| `GraphNotFoundError` | 404 | Tenant graph `mimir_tenant_{id}` doesn't exist |
| `ValueError` | 400 | `max_depth` exceeds ceiling, invalid direction, etc. |

The graph engine raises domain exceptions. The router layer translates them to HTTP responses.

---

## 8. Context Service Migration

### Current Flow (Python BFS)
```
context_service.get_context()
  → _traverse_graph(start_id, relation_types, directions, max_depth)
      → loop:
          _get_relations_for_traversal(current_id, ...)  # SQL query
          add to queue, track visited
      → batch fetch artifacts by ID
```

### Target Flow (Graph Engine)
```
context_service.get_context()
  → graph_engine.traverse(
        tenant_id, [start_id],
        relation_types, direction, max_depth
    )
  → batch fetch artifacts by discovered IDs (existing logic)
```

The context service's `_traverse_graph` and `_get_relations_for_traversal` methods are replaced by a single `graph_engine.traverse()` call. The hints pipeline, temporal filtering, and artifact hydration remain in the context service.

**Note**: The context service currently returns `relation_path` (the sequence of relation types traversed to reach each artifact). If the graph engine's Traverse operation returns only artifact IDs + depth, the path detail is lost. The engineer should decide:
- Option A: Traverse returns paths (richer, matches context service needs)
- Option B: Traverse returns only IDs + depth; context service loses path detail (simpler engine, path detail arguably not critical for most RAG use cases)

I recommend **Option B** for the initial implementation. Path detail can be added later if needed, and FindPaths covers the explicit path-finding use case.

---

## 9. Phase 2: Graph-Scoped Search (API Changes)

Once the engine is working and the context service is migrated, add graph scoping to the search API.

### 9.1 Schema Addition (`schemas/search.py`)

```python
class GraphScope(BaseModel):
    root_ids: list[UUID] = Field(..., min_length=1, max_length=10)
    relation_types: list[str] | None = None
    direction: str = Field("both", pattern="^(outgoing|incoming|both)$")
    max_depth: int = Field(3, ge=1, le=20)
```

Add to `UnifiedSearchRequest`:
```python
graph_scope: GraphScope | None = Field(None, description="...")
```

### 9.2 Validation Rules

- `graph_scope` and `scope_artifact_id` are mutually exclusive (422 if both provided)
- When `scope_artifact_id` is present, internally create `GraphScope(root_ids=[scope_artifact_id], relation_types=["parent_of"], direction="outgoing", max_depth=20)`
- `graph_scope` works with all ranking strategies (fulltext, semantic, hybrid, similar)
- `graph_scope` is **not** compatible with `path_query` (Phase 3)

### 9.3 Search Orchestrator Changes (`routers/search.py`)

In `unified_search()`, after strategy inference and before delegation:

```python
scope_ids: set[UUID] | None = None

if request.graph_scope:
    result = await graph_engine.traverse(
        tenant_id=x_tenant_id,
        start_artifact_ids=request.graph_scope.root_ids,
        relation_types=request.graph_scope.relation_types,
        direction=request.graph_scope.direction,
        max_depth=request.graph_scope.max_depth,
    )
    scope_ids = set(result.artifact_ids)
elif request.scope_artifact_id:
    # Backward-compat: translate to graph traversal
    result = await graph_engine.traverse(
        tenant_id=x_tenant_id,
        start_artifact_ids=[request.scope_artifact_id],
        relation_types=["parent_of"],
        direction="outgoing",
        max_depth=20,
    )
    scope_ids = set(result.artifact_ids)
```

Then pass `scope_ids` to the search service functions as the existing `artifact_id IN (...)` filter.

### 9.4 Deprecation

Add to `scope_artifact_id` field:
```python
scope_artifact_id: UUID | None = Field(
    None,
    deprecated=True,
    description="DEPRECATED: Use graph_scope instead. Restricts to parent_of descendants only.",
)
```

---

## 10. Testing Strategy

### Unit Tests (`tests/unit/test_graph_engine.py`)
- Cypher generation: verify correct Cypher strings for each combination of parameters
- Input validation: max_depth ceiling, invalid direction, empty start_ids
- Error translation: GraphScopeTooLargeError, timeout handling

### Integration Tests (`tests/integration/test_graph_traversal.py`)
Require running PostgreSQL with AGE. Use the existing test infrastructure.

**Setup**: Create a tenant, create artifacts with known graph structure:
```
A → B → C → D       (chain, depth 3)
A → E                (branch from A)
C → F → G            (branch from C)
H → A                (incoming to A)
X (disconnected)     (no edges)
```

**Test cases**:
- Traverse from A, depth 1, outgoing → {B, E}
- Traverse from A, depth 3, outgoing → {B, C, D, E, F, G}
- Traverse from A, depth 1, incoming → {H}
- Traverse from A, depth 1, both → {B, E, H}
- Traverse from A, depth 3, relation_types=["parent_of"] → only parent_of edges followed
- Traverse from X, any depth → empty result
- Traverse from A, include_start=True → includes A in results
- Depth map correctness: B=1, C=2, D=3
- Result set limit exceeded → GraphScopeTooLargeError
- Find paths A→D → [A→B→C→D]
- Find paths A→X → empty (disconnected)

### Integration Tests (`tests/integration/test_graph_search.py`) — Phase 2
- Graph-scoped fulltext search: only returns results within scope
- Graph-scoped semantic search: same
- `scope_artifact_id` backward compatibility: same results as before
- `graph_scope` + `scope_artifact_id` → 422

---

## 11. Delivery Checklist

### Spike (must complete before implementation)

- [ ] Create `scripts/age_cypher_spike.py` — test all Cypher patterns from §5.1
- [ ] Document results in `docs/age-cypher-spike-results.md`
- [ ] Review spike results with architect

### Phase 1: Graph Traversal Engine

- [ ] Add graph engine config to `config.py` (§6)
- [ ] Create `schemas/graph.py` — TraversalResult, PathStep, PathResult, GraphScopeTooLargeError
- [ ] Create `services/graph_engine.py` — `traverse()` operation
- [ ] Add `find_paths()` operation to graph engine
- [ ] Unit tests: Cypher generation, input validation, error handling
- [ ] Integration tests: full traversal test suite (§10)
- [ ] Migrate `context_service._traverse_graph()` → `graph_engine.traverse()`
- [ ] Verify existing context service integration tests still pass
- [ ] Remove dead code: `_get_relations_for_traversal()`, Python BFS queue logic

### Phase 2: Graph-Scoped Search API

- [ ] Add `GraphScope` schema to `schemas/search.py` (or import from `schemas/graph.py`)
- [ ] Add `graph_scope` field to `UnifiedSearchRequest`
- [ ] Add validation: `graph_scope` mutually exclusive with `scope_artifact_id`
- [ ] Implement traverse-then-search in `routers/search.py`
- [ ] Translate `scope_artifact_id` to `graph_engine.traverse()` internally
- [ ] Deprecate `scope_artifact_id` in schema
- [ ] Integration tests: graph-scoped search across all strategies
- [ ] Performance test: scoped search with 1000-artifact scope

### Release

- [ ] Bump version to 4.0.0 in `main.py`
- [ ] Update `search-architecture.md` with graph search section
- [ ] Update `entity-guide.md` with graph search examples
- [ ] Write v3→v4 migration guide
- [ ] Build and push `dawsonlp/mimir-api:v4.0.0`

---

## 12. Files Created/Modified

| File | Action | Phase |
|------|--------|-------|
| `scripts/age_cypher_spike.py` | **New** | Spike |
| `docs/age-cypher-spike-results.md` | **New** | Spike |
| `config.py` | Add 3 graph config fields | 1 |
| `schemas/graph.py` | **New** — TraversalResult, PathStep, PathResult, GraphScope | 1 |
| `services/graph_engine.py` | **New** — traverse(), find_paths() | 1 |
| `services/context_service.py` | Refactor — delegate traversal to graph engine | 1 |
| `schemas/search.py` | Add GraphScope, graph_scope field | 2 |
| `routers/search.py` | Add graph_scope handling before search delegation | 2 |
| `tests/unit/test_graph_engine.py` | **New** | 1 |
| `tests/integration/test_graph_traversal.py` | **New** | 1 |
| `tests/integration/test_graph_search.py` | **New** | 2 |
| `main.py` | Version bump 3.0.0 → 4.0.0 | Release |