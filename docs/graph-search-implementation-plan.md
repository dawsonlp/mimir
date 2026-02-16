# Graph Search Implementation Plan — Mimir v4.0

**Author**: Lead Architect  
**Date**: 2026-02-15  
**Status**: Draft — Awaiting Review  
**Implements**: `docs/graph-search-design.md` (Architecture)  
**Extends**: `docs/age-graph-projection-technical-design.md` (Migration 007)  
**Release**: v4.0.0 (breaking API changes — new graph search fields on unified endpoint)

---

## 1. Current State Assessment

### What's Done (Foundation)

| Component | Status | Details |
|-----------|--------|---------|
| **Apache AGE in PostgreSQL** | ✅ Complete | `postgres-batteries-inc:18` image with AGE 1.7.0, `session_preload_libraries=age` |
| **Per-tenant AGE graphs** | ✅ Complete | Migration 007: `mimir_tenant_{id}` graphs with `Artifact` vertices, `Relation` edges |
| **Trigger-based sync** | ✅ Complete | 6 triggers auto-sync relational → AGE (tenant→graph, artifact→vertex, relation→edge, soft-delete→remove) |
| **Helper functions** | ✅ Complete | `create_tenant_graph()`, `drop_tenant_graph()`, `rebuild_tenant_graph()`, `cypher_escape()` |
| **Connection pool AGE loading** | ✅ Complete | `database.py` configure callback: `LOAD 'age'` + `SET search_path` on every connection |
| **Unified search endpoint** | ✅ Complete | `POST /search` with fulltext/semantic/hybrid/similar strategy inference |
| **Relation filtering** | ✅ Complete | Single-hop `related_to` + `relation_type` + `relation_direction` |
| **Hierarchy scoping** | ✅ Complete | `scope_artifact_id` via recursive CTE on `parent_of` |
| **Context service** | ✅ Complete | Python-side BFS traversal, policy-driven, depth-limited |
| **Phases 1-3** | ✅ Complete | Pagination, metadata filters, hierarchy scoping, deletion, unified search |

### What's NOT Done (Graph Search Capabilities)

| Capability | Status | Architect Reference |
|------------|--------|---------------------|
| **Graph Traversal Engine** | ❌ Not started | graph-search-design.md §4, §5.1 |
| **Multi-hop traversal** | ❌ Not started | graph-search-design.md §3.1 |
| **Graph-scoped search** | ❌ Not started | graph-search-design.md §3.2 |
| **Path finding** | ❌ Not started | graph-search-design.md §3.3 |
| **Pattern matching** | ❌ Not started | graph-search-design.md §3.4 |
| **Context service → graph engine migration** | ❌ Not started | graph-search-design.md §4.3 |
| **Result compositor** | ❌ Not started | graph-search-design.md §4.1 |

### Key Architectural Decision Already Made

The architecture doc (§7.1) chose **per-tenant AGE graphs** over single-graph-with-tenant-property, and **trigger-based sync** over application-layer dual-write. Migration 007 implements this. The AGE graph is a **projection** — the relational tables remain the source of truth.

---

## 2. Gap Analysis: Foundation → Graph Search

The AGE projection (migration 007) handles Phase 0 from graph-search-design.md §11.1. However, the current implementation has properties set for sync purposes but not optimized for the query patterns the Graph Traversal Engine needs:

### 2.1 Vertex Properties (Current vs. Needed)

| Property | Current (007) | Needed for Graph Engine | Action |
|----------|---------------|------------------------|--------|
| `mimir_id` | ✅ UUID as text | ✅ Used in MATCH clauses | None |
| `artifact_type` | ✅ Present | ✅ Pattern matching filter | None |
| `title` | ✅ Present | ✅ Display in path results | None |
| `created_at` | ✅ Present | ✅ Temporal queries | None |
| `deleted_at` | ❌ Not synced | ❌ Not needed — triggers remove on soft-delete | None (trigger handles) |

### 2.2 Edge Properties (Current vs. Needed)

| Property | Current (007) | Needed for Graph Engine | Action |
|----------|---------------|------------------------|--------|
| `mimir_id` | ✅ Relation UUID | ✅ Correlation with relational table | None |
| `relation_type` | ✅ Present | ✅ Multi-hop type filtering | None |
| `confidence` | ✅ Present | Optional for scoring | None |
| `created_at` | ✅ Present | ✅ Temporal queries | None |

### 2.3 Verdict

**The AGE projection from migration 007 is sufficient for the Graph Traversal Engine.** No additional migration is needed. The vertex and edge properties support all four graph operations (traverse, find_paths, match_pattern, graph-scoped search).

---

## 3. Implementation Phases

### Phase 1: Graph Traversal Engine (v4.0.0-alpha)

**Goal**: Internal engine with Traverse and FindPaths operations. No API changes yet.

#### 3.1 New Files

| File | Purpose |
|------|---------|
| `services/graph_engine.py` | Graph Traversal Engine — Traverse, FindPaths, MatchPattern |
| `schemas/graph.py` | GraphScope, PathQuery, PatternSpec, TraversalResult, PathResult schemas |
| `tests/unit/test_graph_engine.py` | Unit tests for Cypher generation |
| `tests/integration/test_graph_traversal.py` | Integration tests against real AGE |

#### 3.2 Graph Engine Operations

**Traverse** (maps to graph-search-design.md §5.1):
```python
async def traverse(
    tenant_id: int,
    start_artifact_ids: list[UUID],
    relation_types: list[str] | None = None,
    directions: list[str] | None = None,  # ["outgoing", "incoming", "both"]
    max_depth: int = 3,
    include_start: bool = False,
) -> TraversalResult:
    """Multi-hop traversal via Cypher. Returns artifact IDs + depth map."""
```

Generates Cypher like:
```cypher
MATCH path = (start)-[*1..{max_depth}]->(reached)
WHERE start.mimir_id IN [{start_ids}]
RETURN DISTINCT reached.mimir_id, length(path)
```

With relation type filtering:
```cypher
MATCH path = (start)-[:Relation*1..{max_depth}]->(reached)
WHERE start.mimir_id IN [{start_ids}]
  AND ALL(r IN relationships(path) WHERE r.relation_type IN [{types}])
RETURN DISTINCT reached.mimir_id, min(length(path))
```

**FindPaths** (maps to §5.1):
```python
async def find_paths(
    tenant_id: int,
    from_artifact_id: UUID,
    to_artifact_id: UUID,
    relation_types: list[str] | None = None,
    max_depth: int = 5,
) -> PathResult:
    """Find shortest paths between two artifacts."""
```

**Note on AGE 1.7.0 Cypher limitations**: AGE's openCypher support does not include `ALL()` predicates on relationships in all contexts, or `shortestPath()`. The technical implementation will need to evaluate what AGE 1.7.0 actually supports and may need to use iterative Cypher or hybrid approaches. This is a known open question from graph-search-design.md §12.1.

#### 3.3 Context Service Migration

Refactor `context_service._traverse_graph()` to call `graph_engine.traverse()` instead of doing Python-side BFS with per-hop SQL queries. This:
- Replaces N+1 queries (one per hop) with a single Cypher query
- Eliminates Python-side visited-set tracking (Cypher handles cycles)
- Preserves the context service's external interface unchanged

#### 3.4 Result Set Size Limit

System-configurable maximum (default 10,000 artifact IDs) as specified in §7.5. If traversal exceeds this, return an error:
```json
{"detail": "Graph scope too broad: traversal returned >10,000 artifacts. Narrow relation_types or reduce max_depth.", "code": "GRAPH_SCOPE_TOO_BROAD"}
```

### Phase 2: Graph-Scoped Search (v4.0.0-beta)

**Goal**: Add `graph_scope` to unified search. This is the highest-value API change.

#### 3.5 Schema Changes (`schemas/search.py`)

Add to `UnifiedSearchRequest`:
```python
graph_scope: GraphScope | None = Field(
    None,
    description="Graph-based scoping: restrict search to artifacts reachable from root(s)"
)
```

Where:
```python
class GraphScope(BaseModel):
    root_ids: list[UUID]
    relation_types: list[str] | None = None
    directions: list[str] | None = None  # default: ["both"]
    max_depth: int = Field(3, ge=1, le=20)
```

#### 3.6 Backward Compatibility

`scope_artifact_id` is preserved as syntactic sugar. When present, internally translated to:
```python
GraphScope(
    root_ids=[scope_artifact_id],
    relation_types=["parent_of"],
    directions=["outgoing"],
    max_depth=20,  # system ceiling
)
```

#### 3.7 Search Orchestrator Flow

1. If `graph_scope` present → call `graph_engine.traverse()` → get artifact ID set
2. Pass artifact ID set as `WHERE artifact_id = ANY(...)` filter to text/semantic search
3. If set exceeds threshold → 422 error

### Phase 3: Path Finding API (v4.0.0-rc)

**Goal**: Add `path_query` to unified search.

Add to `UnifiedSearchRequest`:
```python
path_query: PathQuery | None = Field(
    None,
    description="Find paths between two artifacts (pure graph operation)"
)
```

Where:
```python
class PathQuery(BaseModel):
    from_id: UUID
    to_id: UUID
    relation_types: list[str] | None = None
    max_depth: int = Field(5, ge=1, le=20)
```

Validation: `path_query` is mutually exclusive with ranking inputs (`query`, `query_vector`, `similar_to`).

### Phase 4: Pattern Matching (v4.1.0 — future)

Deferred to a future release. Pattern matching requires the PatternSpec-to-Cypher compiler and careful validation of AGE 1.7.0's `MATCH` capabilities. The graph engine interface will include it from Phase 1 (designed but not implemented), allowing it to be added later without API changes.

---

## 4. Version Strategy

| Release | Contents | Breaking Changes |
|---------|----------|-----------------|
| **v4.0.0-alpha** | Graph Traversal Engine (internal), context service migration | None — internal refactor |
| **v4.0.0-beta** | `graph_scope` on `POST /search` | Additive — new optional field |
| **v4.0.0-rc** | `path_query` on `POST /search`, path response format | Additive — new optional field + response variant |
| **v4.0.0** | Stable release, `scope_artifact_id` deprecated (still works) | Deprecation of `scope_artifact_id` |
| **v4.1.0** | Pattern matching (future) | Additive |

The v4.0 designation is warranted because:
- New graph search capabilities are a major feature addition
- The response format for path queries is structurally different from search results
- `scope_artifact_id` deprecation in favor of `graph_scope` is a semantic shift

---

## 5. Open Questions to Resolve Before Implementation

These map to graph-search-design.md §12 and need answers in the technical design:

| # | Question | Recommended Answer | Rationale |
|---|----------|-------------------|-----------|
| 1 | **AGE Python driver** | Raw psycopg with `ag_catalog.cypher()` SQL calls | Already proven in migration 007 triggers; async-compatible; no new dependency |
| 2 | **Cypher capability gaps in AGE 1.7.0** | Spike: test `shortestPath()`, `ALL()`, variable-length with filters | May need iterative Cypher or multi-query approach |
| 3 | **Direction handling** | Generic `Relation` edges are directional (source→target); for "both", run two queries or use undirected match | AGE stores edges directionally; need to verify `()-[]-()` undirected syntax |
| 4 | **Graph engine error handling** | Timeout per query (configurable, default 5s); result set limit (10K); depth ceiling (20) | Prevents runaway traversals |
| 5 | **Path response format** | Flat list of hops: `[{artifact_id, relation_type, direction}, ...]` | Simplest to consume; matches graph-search-design.md §5.1 |

---

## 6. Implementation Checklist

### Phase 1: Graph Traversal Engine

- [ ] **Spike**: Test AGE 1.7.0 Cypher capabilities (variable-length paths, direction, shortestPath, ALL predicate)
- [ ] Create `schemas/graph.py` — GraphScope, PathQuery, TraversalResult, PathResult
- [ ] Create `services/graph_engine.py` — Traverse operation (Cypher via psycopg)
- [ ] Add FindPaths operation to graph engine
- [ ] Add result set size limit (configurable, default 10K)
- [ ] Add query timeout (configurable, default 5s)
- [ ] Migrate `context_service._traverse_graph()` to use `graph_engine.traverse()`
- [ ] Integration tests: traverse single-hop, multi-hop, cycle handling, type filtering, direction filtering
- [ ] Integration tests: find_paths between connected/disconnected artifacts
- [ ] Performance test: traverse on graph with 1000+ artifacts

### Phase 2: Graph-Scoped Search

- [ ] Add `GraphScope` field to `UnifiedSearchRequest`
- [ ] Add strategy validation: graph_scope works with all ranking strategies
- [ ] Implement traverse-then-search in search orchestrator
- [ ] Translate `scope_artifact_id` to `GraphScope` internally (backward compat)
- [ ] Add `scope_artifact_id` deprecation to schema docs
- [ ] Integration tests: graph-scoped fulltext, semantic, hybrid search
- [ ] Performance test: scoped search with 1000-artifact scope set

### Phase 3: Path Finding API

- [ ] Add `PathQuery` field to `UnifiedSearchRequest`
- [ ] Add validation: path_query mutually exclusive with ranking inputs
- [ ] Implement path response format in search router
- [ ] Integration tests: find path, no path exists, max depth reached
- [ ] Update API docs and OpenAPI spec

### Release

- [ ] Bump version to 4.0.0 in `main.py`
- [ ] Update `docker-compose.yaml` image tags
- [ ] Build and push `dawsonlp/mimir-api:v4.0.0`
- [ ] Update `docs/quickstart.md` with graph search examples
- [ ] Update `docs/search-architecture.md` with graph search section
- [ ] Update `docs/entity-guide.md` with graph search workflows
- [ ] Write migration guide (v3→v4)

---

## 7. Recommended Starting Point

**Start with the AGE Cypher spike.** Before writing any production code, we need to validate what AGE 1.7.0 actually supports for the query patterns we need. Create a test script that:

1. Connects to the running postgres with AGE loaded
2. Creates a test graph with known structure
3. Tests: variable-length path match, relation type filtering in paths, undirected traversal, shortestPath (if available), result aggregation
4. Documents what works and what doesn't

This spike resolves open question #2 and informs the graph engine implementation approach. It should take 2-4 hours and prevents building on assumptions about AGE's Cypher support.

---

## Appendix: File Impact Summary

| File | Change Type | Phase |
|------|-------------|-------|
| `services/graph_engine.py` | **New** | 1 |
| `schemas/graph.py` | **New** | 1 |
| `services/context_service.py` | Refactor (delegate to graph engine) | 1 |
| `schemas/search.py` | Add GraphScope, PathQuery fields | 2, 3 |
| `routers/search.py` | Add graph_scope/path_query handling | 2, 3 |
| `services/search_service.py` | Add graph-scoped search composition | 2 |
| `main.py` | Version bump to 4.0.0 | Release |
| `config.py` | Add graph engine config (timeouts, limits) | 1 |
| `tests/integration/test_graph_traversal.py` | **New** | 1 |
| `tests/integration/test_graph_search.py` | **New** | 2 |
| `tests/integration/test_path_finding.py` | **New** | 3 |