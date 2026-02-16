# Graph Traversal Engine — Development Checklist

**Engineer**: Lead Senior Engineer  
**Started**: 2026-02-15  
**Completed**: 2026-02-15  
**References**:
- `docs/graph-engine-technical-design.md` — Approved technical design
- `docs/graph-engine-agreed-approach.md` — Design review decisions + spike findings
- `docs/age-cypher-spike-results.md` — AGE 1.7.0 capability validation

---

## Pre-Implementation (Complete)

- [x] Read and assess technical design document
- [x] Read all supporting docs (architecture, migration 007, context service, search schemas/router, config, database)
- [x] Identify questions/ambiguities for the architect (Q1–Q6)
- [x] Receive architect/stakeholder decisions (D1–D6)
- [x] Write agreed approach document (`docs/graph-engine-agreed-approach.md`)
- [x] Create AGE Cypher spike script (`scripts/age_cypher_spike.py`)
- [x] Run spike against live AGE 1.7.0 instance — **7/8 tests passed**
- [x] Document spike results with implementation decisions (`docs/age-cypher-spike-results.md`)
- [x] Update agreed approach with spike findings (VLP works, ALL() fails, shortestPath() fails, agtype parsing strategy)

---

## Phase 1A: Foundation ✅

- [x] Add graph engine config fields to `backend/src/mimir/config.py`
  - `graph_max_depth: int = 10` (env: `MIMIR_GRAPH_MAX_DEPTH`)
  - `graph_max_result_set: int = 500` (env: `MIMIR_GRAPH_MAX_RESULT_SET`)
  - `graph_query_timeout_seconds: int = 5` (env: `MIMIR_GRAPH_QUERY_TIMEOUT_SECONDS`)

- [x] Create `backend/src/mimir/schemas/graph.py`
  - `TraversalResult` dataclass: `artifact_id`, `depth`, `relation_path`
  - `PathStep` dataclass: `relation_type`, `direction`, `from_artifact_id`, `to_artifact_id`
  - `PathResult` dataclass: `steps`, `length`, `start_artifact_id`, `end_artifact_id`
  - `GraphScopeTooLargeError` exception (with count/limit attrs)
  - `GraphQueryTimeoutError` exception (with timeout_seconds attr)
  - `GraphNotFoundError` exception (with graph_name attr)

---

## Phase 1B: agtype Parser ✅

- [x] Create `backend/src/mimir/services/agtype_parser.py`
  - `parse_agtype_value(raw)` — scalar: strip `::vertex`/`::edge` suffixes, `json.loads()`, handle bool/int/float/null
  - `parse_agtype_collection(raw)` — collection: regex strip all `::vertex`/`::edge` within string, `json.loads()`

- [x] Create `backend/tests/unit/test_agtype_parser.py` — 24 test cases
  - Scalar string, integer, float, boolean, null, non-string passthrough
  - Vertex and edge with `::vertex`/`::edge` suffixes
  - Malformed input error handling
  - Path collections, node collections, relationship collections
  - Empty arrays, single-element arrays, longer paths

---

## Phase 1C: Graph Engine Core ✅

- [x] Create `backend/src/mimir/services/graph_engine.py`
  - `_execute_cypher()` — connection lifecycle + `SET LOCAL statement_timeout`
  - `_build_traverse_cypher()` — pure function: params → Cypher string (outgoing/incoming/both)
  - `_build_find_paths_cypher()` — pure function: params → Cypher string with ORDER BY length
  - `_extract_path_steps()` — parse agtype path into PathStep list with direction inference
  - `_filter_paths_by_relation_types()` — Python-side filtering (AGE 1.7.0 lacks ALL())

- [x] Implement `traverse()` operation
  - Build VLP Cypher query (direction: outgoing/incoming/both)
  - Parse agtype results via `parse_agtype_collection()`
  - Python-side filtering by relation_types
  - Deduplicate by artifact_id (keep shortest path)
  - Handle `include_start` parameter (D2)
  - Enforce `graph_max_result_set` ceiling → `GraphScopeTooLargeError`
  - Return results sorted by depth ascending

- [x] Implement `find_paths()` operation
  - Build VLP Cypher between two specific vertices
  - `ORDER BY length(path) LIMIT N` (no shortestPath() available)
  - Parse path data from agtype
  - Return paths shortest-first

---

## Phase 1D: Unit Tests ✅

- [x] Create `backend/tests/unit/test_graph_engine.py` — 24 test cases
  - Cypher generation: undirected/outgoing/incoming directions
  - Cypher generation: custom limits, depth=1, large depth
  - Path extraction: single-hop outgoing/incoming, two-hop, three-hop, empty path, single vertex
  - Relation type filtering: all match, some don't match, multiple allowed types, empty paths
  - TraversalResult and PathResult construction
  - GraphScopeTooLargeError message and attributes

---

## Phase 1E: Integration Tests ✅

- [x] Create `backend/tests/integration/test_graph_traversal.py`
  - Test graph fixture with known topology (6 artifacts, 5 relations)
  - `test_traverse_depth_1` — from A, depth=1 → {B, E} (+ A)
  - `test_traverse_depth_2` — from A, depth=2 → {B, C, E} (+ A)
  - `test_traverse_full_depth` — from A, depth=10 → all reachable
  - `test_traverse_with_relation_filter` — derived_from only
  - `test_traverse_direction_outgoing` — from C → {D, F}
  - `test_traverse_direction_undirected` — from C → reaches back
  - `test_traverse_include_start_false` — excludes start
  - `test_traverse_sorted_by_depth` — sorted ascending
  - `test_relation_path_data` — correct relation_path with types and directions
  - `test_find_paths_a_to_d` — 3-hop path
  - `test_find_paths_shortest_first` — sorted by length
  - `test_find_paths_no_path` — depth too short
  - `test_find_paths_a_to_e` — 1-hop direct
  - `test_traverse_result_set_limit` — GraphScopeTooLargeError

---

## Phase 1F: Context Service Migration ✅

- [x] Refactor `backend/src/mimir/services/context_service.py`
  - `_traverse_graph()` now delegates to `graph_engine.traverse()` (single Cypher query)
  - Maps policy configs to traverse parameters (relation_types, direction, max_depth)
  - Maps `TraversalResult.relation_path` → `RelationPathItem` for response
  - Batch fetches artifacts by ID from traversal results
  - Removed Python BFS queue logic, visited set, per-hop SQL queries

- [x] Verify: 141 unit tests pass (no regressions)

---

## Phase 2A: Graph-Scoped Search Schema ✅

- [x] Add `GraphScope` model to `backend/src/mimir/schemas/search.py`
  - `root_artifact_id: UUID`
  - `max_depth: int` (default 3, ge=1, le=20)
  - `relation_types: list[str] | None`
  - `direction: str` (default "both", pattern: outgoing|incoming|both)

- [x] Add `graph_scope: GraphScope | None = None` to `UnifiedSearchRequest`

- [x] Add `model_validator` for mutual exclusion: `graph_scope` + `scope_artifact_id` → 422

---

## Phase 2B: Search Orchestrator Wiring ✅

- [x] Add `_resolve_graph_scope()` helper to `backend/src/mimir/routers/search.py`
  - Calls `graph_engine.traverse(include_start=True)` (D2)
  - Returns set of artifact ID strings
  - Maps exceptions to HTTP errors (422, 504, 404)

- [x] Modify `unified_search()` endpoint
  - `graph_scope` → traverse → post-filter search results by artifact IDs
  - `scope_artifact_id` backward compat → convert to GraphScope(max_depth=1, direction="both")
  - Empty traversal → empty search results (short-circuit)

---

## Phase 2C: Graph-Scoped Search Tests ✅

- [x] Create `backend/tests/integration/test_graph_scoped_search.py`
  - `test_graph_scope_fulltext` — depth=1 restricts results
  - `test_graph_scope_deeper_depth` — depth=2 includes more
  - `test_graph_scope_with_relation_filter` — relation_types filtering
  - `test_graph_scope_outgoing_direction` — direction control
  - `test_scope_artifact_id_works` — backward compatibility
  - `test_mutual_exclusion` — both params → 422
  - `test_graph_scope_invalid_direction` — "sideways" → 422
  - `test_graph_scope_invalid_depth` — depth=0 → 422

---

## Release ✅

- [x] Bump version to 4.0.0 in `backend/src/mimir/main.py`
- [x] Update `changelog.md` with graph engine features
- [ ] Update `docs/quickstart.md` with graph_scope search examples
- [ ] Build and push Docker image

---

## Files Created/Modified Summary

| File | Action | Phase |
|------|--------|-------|
| `scripts/age_cypher_spike.py` | ✅ Created | Spike |
| `docs/age-cypher-spike-results.md` | ✅ Created | Spike |
| `docs/graph-engine-agreed-approach.md` | ✅ Created | Pre-impl |
| `docs/graph-engine-development-checklist.md` | ✅ Created + Updated | Pre-impl |
| `backend/src/mimir/config.py` | ✅ Modified — added 3 graph config fields | 1A |
| `backend/src/mimir/schemas/graph.py` | ✅ **New** — TraversalResult, PathStep, PathResult, exceptions | 1A |
| `backend/src/mimir/services/agtype_parser.py` | ✅ **New** — agtype parsing utilities | 1B |
| `backend/tests/unit/test_agtype_parser.py` | ✅ **New** — 24 parser tests | 1B |
| `backend/src/mimir/services/graph_engine.py` | ✅ **New** — traverse(), find_paths(), Cypher builders | 1C |
| `backend/tests/unit/test_graph_engine.py` | ✅ **New** — 24 engine unit tests | 1D |
| `backend/tests/integration/test_graph_traversal.py` | ✅ **New** — 14 traversal integration tests | 1E |
| `backend/src/mimir/services/context_service.py` | ✅ Modified — delegates to graph_engine | 1F |
| `backend/src/mimir/schemas/search.py` | ✅ Modified — added GraphScope, graph_scope, validation | 2A |
| `backend/src/mimir/routers/search.py` | ✅ Modified — graph_scope handling + error mapping | 2B |
| `backend/tests/integration/test_graph_scoped_search.py` | ✅ **New** — 8 graph-scoped search tests | 2C |
| `backend/src/mimir/main.py` | ✅ Modified — version bump 3.0.0 → 4.0.0 | Release |
| `changelog.md` | ✅ Modified — v4.0.0 entry | Release |