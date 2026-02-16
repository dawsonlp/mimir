# Mimir v4.0.0 Release Notes — Graph Traversal Engine

**Release Date**: 2026-02-15  
**API Version**: 4.0.0  
**Docker Image**: `dawsonlp/mimir-api:v4.0.0`  
**Git Tag**: `v4.0.0`

---

## What's New

### Graph Traversal Engine

Mimir now includes a **Cypher-based graph traversal engine** powered by Apache AGE 1.7.0, running inside PostgreSQL alongside pgvector. This replaces the previous Python-side BFS traversal with a single database-side graph query, delivering significant performance improvements.

**Two new operations are available:**

| Operation | Description |
|-----------|-------------|
| `traverse()` | Variable-length path traversal from a starting artifact — configurable depth, direction, and relation type filtering |
| `find_paths()` | Find shortest paths between two artifacts — returns paths sorted by length |

Both operations return **full relation path data** (relation types, directions, from/to artifact IDs at each hop), enabling argument chain validation and provenance tracing.

### Graph-Scoped Search (`graph_scope` parameter)

The unified search endpoint (`POST /search`) now supports a **`graph_scope`** parameter that implements the **traverse-then-search** pattern:

1. Traverse the graph from a root artifact
2. Collect all reachable artifact IDs within the scope
3. Restrict search results to only those artifacts

```json
POST /search
{
  "query": "authentication design",
  "graph_scope": {
    "root_artifact_id": "550e8400-e29b-41d4-a716-446655440000",
    "max_depth": 3,
    "relation_types": ["derived_from", "supports"],
    "direction": "both"
  }
}
```

**GraphScope parameters:**

| Parameter | Default | Description |
|-----------|---------|-------------|
| `root_artifact_id` | required | UUID of the starting artifact |
| `max_depth` | 3 | Traversal depth (1–20) |
| `relation_types` | null (all) | Only follow these relation types |
| `direction` | "both" | `outgoing`, `incoming`, or `both` |

### Context Service Performance Improvement

The context endpoint (`POST /context`) now uses the graph engine internally. The previous implementation made **N+1 SQL queries** (one per hop per artifact during BFS). The new implementation executes a **single Cypher query** inside PostgreSQL.

All existing context policies (direct_relations, derived_lineage, evidence_chain, full_graph) continue to work with the same API contract.

---

## Breaking Changes

**None.** This release is backward-compatible.

- `scope_artifact_id` continues to work — internally converts to `GraphScope(max_depth=1, direction="both")`
- All existing search parameters and context policies are unchanged
- No schema migration changes to existing tables

---

## New Configuration

Three new environment variables (all optional with sensible defaults):

| Variable | Default | Description |
|----------|---------|-------------|
| `MIMIR_GRAPH_MAX_DEPTH` | 10 | Maximum allowed traversal depth |
| `MIMIR_GRAPH_MAX_RESULT_SET` | 500 | Maximum vertices returned per traversal |
| `MIMIR_GRAPH_QUERY_TIMEOUT_SECONDS` | 5 | Per-query timeout (DB-enforced) |

---

## New Error Responses

| Error | HTTP Code | When |
|-------|-----------|------|
| `GRAPH_SCOPE_TOO_LARGE` | 422 | Traversal result exceeds `MIMIR_GRAPH_MAX_RESULT_SET` |
| `GRAPH_QUERY_TIMEOUT` | 504 | Cypher query exceeds `MIMIR_GRAPH_QUERY_TIMEOUT_SECONDS` |
| `GRAPH_NOT_FOUND` | 404 | Tenant graph doesn't exist (tenant has no graph projection) |

---

## Validation Rules

- `graph_scope` and `scope_artifact_id` are **mutually exclusive** — providing both returns 422
- `graph_scope.direction` must be one of: `outgoing`, `incoming`, `both`
- `graph_scope.max_depth` must be 1–20

---

## For Agent Developers

### Using Graph-Scoped Search

When your agent needs to search within the context of a specific artifact (e.g., "find all evidence related to this decision"), use `graph_scope` instead of fetching IDs manually:

```python
# Before (manual traversal + search)
context = await client.post("/context", json={"artifact_id": root_id, "policy": "full_graph"})
ids = [a["artifact"]["id"] for a in context["context"]]
# ... manual filtering

# After (single request)
results = await client.post("/search", json={
    "query": "authentication",
    "graph_scope": {
        "root_artifact_id": root_id,
        "max_depth": 3,
        "relation_types": ["derived_from", "supports"]
    }
}, headers={"X-Tenant-ID": str(tenant_id)})
```

### Find Paths Between Artifacts

The `find_paths()` operation is available via the graph engine module but not yet exposed as an API endpoint (planned for Phase 5). Contact the platform team if your agent needs shortest-path queries.

---

## Infrastructure

- **Database**: PostgreSQL 18 with Apache AGE 1.7.0 + pgvector
- **Migrations**: 007_age_graph_projection creates per-tenant graphs with trigger-based sync
- **Docker**: Multi-arch (amd64 + arm64), non-root user, health checks
- **All 7 migrations applied on fresh start** — verified clean bootstrap

---

## Testing

- 141 unit tests pass (48 new for graph engine + agtype parser)
- Integration test suites ready for graph traversal (14 tests) and graph-scoped search (8 tests)

---

## What's Next (Phase 5)

- Match pattern queries (structured graph pattern matching)
- Graph-aware relevance scoring (combine graph distance with text/semantic scores)
- Graph analytics endpoints (stats, neighbors, visualization data)
- Performance optimization (AGE 1.8+ features, benchmarking)

---

**Questions?** Contact the platform engineering team or file an issue in the [mimir repo](https://github.com/dawsonlp/mimir).