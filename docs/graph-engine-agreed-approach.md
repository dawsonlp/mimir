# Graph Traversal Engine — Agreed Approach

**Date**: 2026-02-15  
**Participants**: Lead Architect, Lead Senior Engineer, Stakeholder  
**References**: `docs/graph-engine-technical-design.md` (approved design)  
**Purpose**: Capture decisions from the senior engineer's design review before implementation begins.

---

## Decision Log

### D1: Connection Lifecycle

**Decision**: The graph engine acquires its own connection via `get_connection()` internally. The `traverse()` and `find_paths()` signatures do **not** accept a connection parameter.

**Rationale**: All operations are read-only. The graph is a trigger-synced projection of relational data — triggers fire synchronously within the write transaction, so by the time any reader sees relational data, the graph is already consistent. Separate connections for traversal and subsequent search create no meaningful inconsistency risk. This matches the existing service-layer pattern throughout the codebase.

---

### D2: `include_start` Behavior

**Decision**: Both `scope_artifact_id` backward-compat translation and `graph_scope` traversal will use `include_start=True`.

**Rationale**: Stakeholder confirmed that scoping to a root artifact should include the root itself in search results. The current recursive CTE includes the root. Excluding it would be a silent breaking change.

**Design amendment**: §9.3 of the technical design should read:
```python
# scope_artifact_id backward-compat
result = await graph_engine.traverse(
    tenant_id=x_tenant_id,
    start_artifact_ids=[request.scope_artifact_id],
    relation_types=["parent_of"],
    direction="outgoing",
    max_depth=20,
    include_start=True,  # Root must be included (matches current CTE behavior)
)

# graph_scope — also include roots
result = await graph_engine.traverse(
    tenant_id=x_tenant_id,
    start_artifact_ids=request.graph_scope.root_ids,
    relation_types=request.graph_scope.relation_types,
    direction=request.graph_scope.direction,
    max_depth=request.graph_scope.max_depth,
    include_start=True,  # Roots are part of the searchable scope
)
```

---

### D3: `relation_path` — Complete or Absent

**Decision**: The `traverse()` operation **must return full path information** (the sequence of relations and intermediate artifacts to reach each result). The `relation_path` field in `ContextArtifact` must be correctly populated, not left empty.

**Stakeholder rationale**: A core use case is argument chain validation — following chains like `statement → counter-argument → response → evidence`. Understanding these structures requires the actual graph paths, not just depth statistics. The stakeholder explicitly stated: "I would prefer it be either absent or complete and correct when we release the functionality."

**Design amendment**: This changes the technical design's recommendation from **Option B** (IDs + depth only) to **Option A** (full paths). The `TraversalResult` must include path information:

```python
@dataclass
class TraversalResult:
    artifact_ids: list[UUID]
    depth_map: dict[UUID, int]           # artifact_id → shortest distance
    paths: dict[UUID, list[PathStep]]    # artifact_id → path from nearest start node
```

**Risk**: This depends on AGE 1.7.0's ability to return path data from variable-length path queries. The spike (§5.1, Tests 1 and 5) must validate whether `path` variables and `length(path)` work correctly. If AGE cannot return path details from variable-length queries, the fallback is iterative single-hop Cypher where path is built in Python (similar to the current BFS but using Cypher per hop instead of SQL).

**Impact on implementation timeline**: This adds complexity to the Cypher query design and agtype parsing. The engineer should assess spike results before committing to a path-returning approach vs. iterative hop-by-hop approach.

---

### D4: MatchPattern — Deferred to Phase 3+

**Decision**: MatchPattern is deferred, not dropped. It remains in the architecture roadmap.

**Implementation guidance**: The Cypher builder should be structured as pure functions with clean separation between query construction and execution. This makes MatchPattern straightforward to add later without requiring structural changes. No over-engineering needed — just don't hard-code MATCH pattern shapes into the execution layer.

---

### D5: `related_to` Coexistence

**Decision**: `related_to` is unchanged and fully compatible with `graph_scope`. They serve complementary purposes:
- `graph_scope`: pre-search scope narrowing (limit search universe to subgraph)
- `related_to`: post-search relation filter (results must have specific relation to X)

No changes to `related_to` behavior or validation.

---

### D6: Timeout Mechanism

**Decision**: Use PostgreSQL `SET LOCAL statement_timeout` as the sole timeout mechanism.

**Implementation**:
```python
async with get_connection() as conn:
    await conn.execute("SET LOCAL statement_timeout = %s", (timeout_ms,))
    result = await conn.execute(cypher_query)
```

**Rationale**: Transaction-scoped, automatically resets when the connection returns to the pool, and ensures the database kills the query cleanly (no orphaned server-side execution). `asyncio.wait_for()` is not used because it would leave server-side queries running.

---

## Revised Implementation Sequence

The decisions above affect the implementation plan as follows:

### Spike (unchanged — mandatory first step)
1. Create `scripts/age_cypher_spike.py` — all 7 Cypher patterns from §5.1
2. **Additional spike focus**: Test whether AGE returns full path data (vertex/edge sequences) from variable-length path queries. This is now critical for D3.
3. Document results in `docs/age-cypher-spike-results.md`
4. Review with architect — **spike results determine whether path data comes from single Cypher queries or iterative hop-by-hop approach**

### Phase 1: Graph Traversal Engine
- `TraversalResult` includes `paths: dict[UUID, list[PathStep]]` (per D3)
- `traverse()` must populate `relation_path` data for the context service
- If AGE supports path extraction from VLP queries: single Cypher query returning paths
- If AGE does not: iterative single-hop Cypher (build path in Python, still using Cypher per hop — an improvement over current SQL per hop)
- All other items from the technical design's delivery checklist remain the same

### Phase 2: Graph-Scoped Search API
- Both `graph_scope` and `scope_artifact_id` use `include_start=True` (per D2)
- `related_to` unchanged (per D5)
- All other items from the technical design's delivery checklist remain the same

---

## Spike Results (2026-02-15)

Full results: `docs/age-cypher-spike-results.md`

### Resolved Items

| Item | Result | Decision |
|------|--------|----------|
| Can AGE return path data from VLP queries? | ✅ Yes — `nodes(path)` and `relationships(path)` return full vertex/edge data | Single VLP query approach viable for path extraction |
| agtype parsing for path objects | ✅ All agtype values return as Python `str`. Paths/collections have `::vertex`/`::edge` suffixes | Build `parse_agtype_value()` and `parse_agtype_collection()` helpers using regex strip + `json.loads()` |
| Iterative vs single-query approach for `traverse()` | **Single VLP query** with Python-side relation type filtering | AGE doesn't support `ALL()` predicates, so relation types cannot be filtered in Cypher. Single query returns all paths; Python filters by `relation_type` on each edge. |
| `shortestPath()` support | ❌ Not supported in AGE 1.7.0 | `find_paths()` uses VLP + `ORDER BY length(path) LIMIT N` |

### Implications for Implementation

1. **`traverse()` approach**: Execute one VLP Cypher query with `nodes(path)` + `relationships(path)` → parse agtype → filter paths in Python by `relation_type` → build `TraversalResult` with full `paths` data. This satisfies D3 (complete relation_path).

2. **`find_paths()` approach**: Execute VLP between two specific vertices with `ORDER BY length(path) LIMIT M`. No `shortestPath()` available.

3. **agtype parser** (new internal module): Required for all Cypher result processing. Two functions:
   - `parse_agtype_value(raw: str)`: Strip quotes from scalars, handle bool/int/float
   - `parse_agtype_collection(raw: str)`: Regex strip `::vertex`/`::edge`, then `json.loads()`

4. **Performance guardrails**: VLP depth limit (`*1..N`), `LIMIT` clause, and `SET LOCAL statement_timeout` together prevent runaway queries. Relation type filtering in Python is acceptable because depth limits constrain the result set.

### Remaining Open Items

| Item | Resolved By |
|------|-------------|
| MatchPattern query builder extensibility | Phase 3+ design |
