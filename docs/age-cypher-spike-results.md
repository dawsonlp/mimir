# AGE Cypher Spike — Results

**Date**: 2026-02-15T16:45:49
**AGE Version**: 1.7.0  
**PostgreSQL Image**: dawsonlp/postgres-batteries-inc:18  
**Driver**: psycopg 3.3.2  

---

## Summary: 7/8 passed

### ✅ PASS — Test 1: Variable-length path (outgoing)

**Notes**: All expected IDs found

**Output**:
```
Returned 5 rows. Cleaned IDs: ['B', 'F', 'D', 'C', 'E']
```


### ✅ PASS — Test 2: Variable-length path (undirected/both)

**Notes**: All expected IDs found

**Output**:
```
Returned 6 rows. Cleaned IDs: ['B', 'H', 'F', 'D', 'C', 'E']
```


### ✅ PASS — Test 3: Relation type filtering in VLP

**Notes**: 3A=OK, 3B=FAIL, 3C=OK, 3D=OK

**Output**:
```
3A: Returned 5 rows.
  E depth=1
  B depth=1
  C depth=2
  F depth=3
  D depth=3
3B FAILED: syntax error at or near "("
LINE 1: ...d = 'b7b43595-409d-4b59-a3d3-c8fd1e2255f8' AND ALL(rel IN re...
                                                             ^
3C: Returned 5 rows.
  First rels type: str
  First rels value: '[{"id": 1125899906842629, "label": "Relation", "end_id": 844424930131976, "start_id": 844424930131972, "properties": {"mimir_id": "dca7298e-1bdc-4ac0-ba7d-4db23bff7039", "confidence": 1.0, "created_at": "2026-01-01T00:00:00Z", "relation_type": "supports"}}::edge]'
3D: Returned 5 rows.
  First nodes type: str
  First nodes value: '[{"id": 844424930131972, "label": "Artifact", "properties": {"title": "Test Artifact A", "mimir_id": "b7b43595-409d-4b59-a3d3-c8fd1e2255f8", "created_at": "2026-01-01T00:00:00Z", "artifact_type": "document"}}::vertex, {"id": 844424930131976, "label": "Artifact", "properties": {"title": "Test Artifa

```


### ❌ FAIL — Test 4: shortestPath()

**Notes**: shortestPath() NOT supported — fallback needed

**Error**:
```
syntax error at or near "shortestPath"
LINE 1: ...catalog.cypher('mimir_tenant_99999', $$ MATCH p = shortestPa...
                                                             ^
```


### ✅ PASS — Test 5: length() function

**Notes**: length() works. Depths correct: True

**Output**:
```
Returned 6 rows.
Depth map: {'E': 1, 'B': 1, 'C': 2, 'F': 3, 'G': 4, 'D': 3}
Expected depths correct: True

```


### ✅ PASS — Test 6: LIMIT clause

**Notes**: LIMIT respected: True

**Output**:
```
Returned 3 rows (LIMIT 3).

```


### ✅ PASS — Test 7: agtype parsing

**Notes**: See output for agtype parsing details

**Output**:
```
=== Property returns ===
  mimir_id: type=str, repr='"b7b43595-409d-4b59-a3d3-c8fd1e2255f8"'
  title: type=str, repr='"Test Artifact A"'
  artifact_type: type=str, repr='"document"'
  vertex: type=str, repr='{"id": 844424930131972, "label": "Artifact", "properties": {"title": "Test Artifact A", "mimir_id": "b7b43595-409d-4b59-a3d3-c8fd1e2255f8", "created_at": "2026-01-01T00:00:00Z", "artifact_type": "doc

=== Edge returns ===
  edge: type=str, repr='{"id": 1125899906842626, "label": "Relation", "end_id": 844424930131973, "start_id": 844424930131972, "properties": {"mimir_id": "b7a0c0cc-4852-4b3d-b8c0-cb13d323390e", "confidence": 1.0, "created_at
  relation_type: type=str, repr='"derived_from"'
  mimir_id: type=str, repr='"b7a0c0cc-4852-4b3d-b8c0-cb13d323390e"'

=== Path return (single hop) ===
  type=str
  repr='[{"id": 844424930131972, "label": "Artifact", "properties": {"title": "Test Artifact A", "mimir_id": "b7b43595-409d-4b59-a3d3-c8fd1e2255f8", "created_at": "2026-01-01T00:00:00Z", "artifact_type": "document"}}::vertex, {"id": 1125899906842626, "label": "Relation", "end_id": 844424930131973, "start_id": 844424930131972, "properties": {"mimir_id": "b7a0c0cc-4852-4b3d-b8c0-cb13d323390e", "confidence": 1.0, "created_at": "2026-01-01T00:00:00Z", "relation_type": "derived_from"}}::edge, {"id": 8444249
  str=[{"id": 844424930131972, "label": "Artifact", "properties": {"title": "Test Artifact A", "mimir_id": "b7b43595-409d-4b59-a3d3-c8fd1e2255f8", "created_at": "2026-01-01T00:00:00Z", "artifact_type": "document"}}::vertex, {"id": 1125899906842626, "label": "Relation", "end_id": 844424930131973, "start_id": 844424930131972, "properties": {"mimir_id": "b7a0c0cc-4852-4b3d-b8c0-cb13d323390e", "confidence": 1.0, "created_at": "2026-01-01T00:00:00Z", "relation_type": "derived_from"}}::edge, {"id": 84442493

=== Scalar returns ===
  length(path): type=str, repr='1'
  int(42): type=str, repr='42'
  float(3.14): type=str, repr='3.14'
  bool(true): type=str, repr='true'

```


### ✅ PASS — Test 8: Path data extraction (D3 critical)

**Notes**: See output for path data structure details

**Output**:
```
Returned 5 path rows.

--- Path 1 → E (depth 1) ---
  python type: str
  str (first 400 chars): [{"id": 844424930131972, "label": "Artifact", "properties": {"title": "Test Artifact A", "mimir_id": "b7b43595-409d-4b59-a3d3-c8fd1e2255f8", "created_at": "2026-01-01T00:00:00Z", "artifact_type": "document"}}::vertex, {"id": 1125899906842629, "label": "Relation", "end_id": 844424930131976, "start_id": 844424930131972, "properties": {"mimir_id": "dca7298e-1bdc-4ac0-ba7d-4db23bff7039", "confidence":
  JSON parse: FAILED (not valid JSON)

--- Path 2 → B (depth 1) ---
  python type: str
  str (first 400 chars): [{"id": 844424930131972, "label": "Artifact", "properties": {"title": "Test Artifact A", "mimir_id": "b7b43595-409d-4b59-a3d3-c8fd1e2255f8", "created_at": "2026-01-01T00:00:00Z", "artifact_type": "document"}}::vertex, {"id": 1125899906842626, "label": "Relation", "end_id": 844424930131973, "start_id": 844424930131972, "properties": {"mimir_id": "b7a0c0cc-4852-4b3d-b8c0-cb13d323390e", "confidence":
  JSON parse: FAILED (not valid JSON)

--- Path 3 → C (depth 2) ---
  python type: str
  str (first 400 chars): [{"id": 844424930131972, "label": "Artifact", "properties": {"title": "Test Artifact A", "mimir_id": "b7b43595-409d-4b59-a3d3-c8fd1e2255f8", "created_at": "2026-01-01T00:00:00Z", "artifact_type": "document"}}::vertex, {"id": 1125899906842626, "label": "Relation", "end_id": 844424930131973, "start_id": 844424930131972, "properties": {"mimir_id": "b7a0c0cc-4852-4b3d-b8c0-cb13d323390e", "confidence":
  JSON parse: FAILED (not valid JSON)

--- Path 4 → F (depth 3) ---
  python type: str
  str (first 400 chars): [{"id": 844424930131972, "label": "Artifact", "properties": {"title": "Test Artifact A", "mimir_id": "b7b43595-409d-4b59-a3d3-c8fd1e2255f8", "created_at": "2026-01-01T00:00:00Z", "artifact_type": "document"}}::vertex, {"id": 1125899906842626, "label": "Relation", "end_id": 844424930131973, "start_id": 844424930131972, "properties": {"mimir_id": "b7a0c0cc-4852-4b3d-b8c0-cb13d323390e", "confidence":
  JSON parse: FAILED (not valid JSON)

--- Path 5 → D (depth 3) ---
  python type: str
  str (first 400 chars): [{"id": 844424930131972, "label": "Artifact", "properties": {"title": "Test Artifact A", "mimir_id": "b7b43595-409d-4b59-a3d3-c8fd1e2255f8", "created_at": "2026-01-01T00:00:00Z", "artifact_type": "document"}}::vertex, {"id": 1125899906842626, "label": "Relation", "end_id": 844424930131973, "start_id": 844424930131972, "properties": {"mimir_id": "b7a0c0cc-4852-4b3d-b8c0-cb13d323390e", "confidence":
  JSON parse: FAILED (not valid JSON)

=== Separate nodes/relationships extraction ===

  Path to E:
    nodes type: str, val: '[{"id": 844424930131972, "label": "Artifact", "properties": {"title": "Test Artifact A", "mimir_id": "b7b43595-409d-4b59-a3d3-c8fd1e2255f8", "created_at": "2026-01-01T00:00:00Z", "artifact_type": "document"}}::vertex, {"id": 844424930131976, "label": "Artifact", "properties": {"title": "Test Artifa
    rels  type: str, val: '[{"id": 1125899906842629, "label": "Relation", "end_id": 844424930131976, "start_id": 844424930131972, "properties": {"mimir_id": "dca7298e-1bdc-4ac0-ba7d-4db23bff7039", "confidence": 1.0, "created_at": "2026-01-01T00:00:00Z", "relation_type": "supports"}}::edge]'
    nodes JSON parse failed
    rels JSON parse failed

  Path to B:
    nodes type: str, val: '[{"id": 844424930131972, "label": "Artifact", "properties": {"title": "Test Artifact A", "mimir_id": "b7b43595-409d-4b59-a3d3-c8fd1e2255f8", "created_at": "2026-01-01T00:00:00Z", "artifact_type": "document"}}::vertex, {"id": 844424930131973, "label": "Artifact", "properties": {"title": "Test Artifa
    rels  type: str, val: '[{"id": 1125899906842626, "label": "Relation", "end_id": 844424930131973, "start_id": 844424930131972, "properties": {"mimir_id": "b7a0c0cc-4852-4b3d-b8c0-cb13d323390e", "confidence": 1.0, "created_at": "2026-01-01T00:00:00Z", "relation_type": "derived_from"}}::edge]'
    nodes JSON parse failed
    rels JSON parse failed

  Path to C:
    nodes type: str, val: '[{"id": 844424930131972, "label": "Artifact", "properties": {"title": "Test Artifact A", "mimir_id": "b7b43595-409d-4b59-a3d3-c8fd1e2255f8", "created_at": "2026-01-01T00:00:00Z", "artifact_type": "document"}}::vertex, {"id": 844424930131973, "label": "Artifact", "properties": {"title": "Test Artifa
    rels  type: str, val: '[{"id": 1125899906842626, "label": "Relation", "end_id": 844424930131973, "start_id": 844424930131972, "properties": {"mimir_id": "b7a0c0cc-4852-4b3d-b8c0-cb13d323390e", "confidence": 1.0, "created_at": "2026-01-01T00:00:00Z", "relation_type": "derived_from"}}::edge, {"id": 1125899906842627, "label
    nodes JSON parse failed
    rels JSON parse failed

```


---

## Decisions for Implementation

### Key Findings

1. **agtype is always `str`**: Every value returned from `ag_catalog.cypher()` arrives as a Python `str`. String properties are double-quoted (`"derived_from"`). Integers/floats/bools are unquoted strings (`"1"`, `"3.14"`, `"true"`). Vertices, edges, and paths include `::vertex`, `::edge` type suffixes that break standard `json.loads()`.

2. **Path data structure**: Paths come back as `[{...}::vertex, {...}::edge, {...}::vertex, ...]`. The `nodes(path)` and `relationships(path)` functions return the same format but with only vertices or only edges. The JSON content within each element contains `id`, `label`, `properties`, and for edges: `start_id`, `end_id`.

3. **ALL() predicate not supported**: AGE 1.7.0 does not support list comprehension predicates like `ALL(r IN relationships(path) WHERE ...)`. This means relation type filtering cannot be done in Cypher for variable-length paths.

4. **shortestPath() not supported**: AGE 1.7.0 does not support the `shortestPath()` function. Path finding must use VLP queries ordered by length.

### Decision Table

| Pattern | Works? | Chosen Approach |
|---------|--------|-----------------|
| Variable-length path (outgoing) | ✅ Yes | Use directly: `MATCH (s)-[:Relation*1..N]->(t)` |
| Variable-length path (undirected) | ✅ Yes | Use directly: `MATCH (s)-[:Relation*1..N]-(t)` |
| Relation type filtering in VLP | ❌ ALL() fails | Fetch all VLP paths, use `relationships(path)` to get edges, filter `relation_type` in Python |
| shortestPath() | ❌ Not supported | Use VLP with `ORDER BY length(path) LIMIT N` for `find_paths()` |
| length() function | ✅ Yes | Use for depth calculation in all queries |
| LIMIT clause | ✅ Yes | Use for result set enforcement |
| agtype parsing | ✅ All strings | Build `parse_agtype()` helper: strip `::vertex`/`::edge` suffixes with regex, then `json.loads()`. Strip quotes from scalar properties. |
| Path data extraction (D3) | ✅ Data available | Use `nodes(path)` + `relationships(path)` to extract full path data. Parse with agtype helper. Populates `relation_path` for context service. |

### Implementation Approach for `traverse()`

Since relation type filtering must be done in Python, the engine will:
1. Execute VLP Cypher query **without** relation type filter (returns all reachable paths)
2. Use `nodes(path)` and `relationships(path)` to get structured path data
3. Parse agtype strings (strip `::vertex`/`::edge`, JSON parse)
4. Filter paths in Python: reject any path containing an edge whose `relation_type` is not in the allowed set
5. Build `TraversalResult` with `artifact_ids`, `depth_map`, and `paths`

For large graphs, this is acceptable because:
- The VLP depth limit (`*1..N`) constrains the explosion
- `LIMIT` + result set ceiling provides a hard stop
- `statement_timeout` prevents runaway queries

### Implementation Approach for `find_paths()`

Without `shortestPath()`:
1. Execute: `MATCH path = (a)-[:Relation*..N]-(b) WHERE ... RETURN path, length(path) ORDER BY length(path) LIMIT M`
2. Parse path data from agtype
3. Return paths shortest-first

### agtype Parser Design

```python
import re, json

# Strip ::vertex and ::edge type annotations from agtype strings
_AGTYPE_SUFFIX = re.compile(r'::(?:vertex|edge)')

def parse_agtype_value(raw: str) -> any:
    """Parse a single agtype scalar value (property return)."""
    # Quoted string → strip quotes
    if raw.startswith('"') and raw.endswith('"'):
        return raw[1:-1]
    # Boolean
    if raw == 'true': return True
    if raw == 'false': return False
    if raw == 'null': return None
    # Numeric
    try: return int(raw)
    except ValueError: pass
    try: return float(raw)
    except ValueError: pass
    return raw

def parse_agtype_collection(raw: str) -> list[dict]:
    """Parse an agtype list (path, nodes, relationships)."""
    cleaned = _AGTYPE_SUFFIX.sub('', raw)
    return json.loads(cleaned)
```
