# Mimir Enhancement Requests

**From**: Developer1 Agent Team  
**Date**: 2026-02-13  
**Context**: Developer1 is Mimir's first integration consumer. We use Mimir as a knowledge graph to ingest project source code, generate embeddings for function-level chunks, and perform semantic search during automated code evaluation. These requests arise from real production issues encountered during our first end-to-end run against a 132-file Python project.

---

## 1. Scoped Semantic Search (Critical)

### The Need

When performing semantic search via `POST /search/semantic`, results are returned from the entire Mimir database with no way to restrict the search scope. In a multi-project or multi-run scenario, this means results from unrelated projects, stale data from previous runs, or even accidentally ingested third-party library code contaminate every search.

### What Happened

During our first run, a directory scanner bug caused 6,006 files from `.venv/site-packages` to be ingested before we killed the process. We fixed the scanner and re-ran with the correct 132 files. But semantic search still returns results from both runs — the 6,006 garbage artifacts outnumber the real ones 45:1, and their embeddings dominate search results for every query.

The result: 37 out of 37 "not met" evaluations were false negatives. The evaluator was examining Jinja2 template code, aiohttp internals, and Click library source instead of the actual project code.

### Current Workaround

We post-filter search results client-side by checking `metadata.relative_path` against a known set of project file paths. This is wasteful — we over-fetch (`limit=20`) hoping enough valid results survive filtering, but if the top 20 are all contaminated, we get nothing useful.

### Proposed Enhancement

Add an optional `parent_artifact_id` parameter to `POST /search/semantic` that restricts results to artifacts that are descendants (children, grandchildren, etc.) of the specified artifact.

```json
{
  "query_vector": [...],
  "embedding_type": "nomic",
  "limit": 10,
  "parent_artifact_id": "uuid-of-project-artifact"
}
```

This is the single most impactful enhancement for any consumer that organizes data hierarchically (projects → files → chunks), which we expect to be the common case.

### Alternative Approaches

If full ancestor-tree filtering is complex to implement, even a simpler `parent_artifact_id` filter (direct children only, not recursive) combined with our existing hierarchy (project → file → chunk, where only chunks have embeddings) would solve the problem — search would return chunks under file artifacts under the specified project.

A `metadata` filter (e.g., `metadata.relative_path IN [...]`) would also work but is less general and requires the consumer to maintain the filter set.

---

## 2. Artifact Deletion with Cascade (Critical)

### The Need

There is currently no `DELETE` endpoint for artifacts. Once an artifact is created, it exists permanently. This means:

- **No cleanup after failed runs** — Our aborted first run left 6,006 artifacts with embeddings that permanently pollute search
- **No idempotent re-runs** — Running the same workflow twice creates duplicate artifacts with duplicate embeddings, doubling search noise
- **No data lifecycle management** — Stale analysis results accumulate indefinitely

### Current Workaround

None. The contaminated data from our first run is permanently in the database. We cannot remove it. Every future search against this Mimir instance will include it.

### Proposed Enhancement

Add `DELETE /artifacts/{id}` with an optional cascade parameter:

```
DELETE /artifacts/{id}?cascade=true
```

Behavior:
- **Without cascade**: Delete the artifact only. Fail if it has children or relations (referential integrity).
- **With cascade**: Delete the artifact and all its descendants (children, grandchildren), their embeddings, and their relations. This is the common case for cleaning up a project evaluation tree.

This enables idempotent workflows: before ingesting, check if a project artifact already exists, delete it with cascade, then re-ingest fresh.

---

## 3. Parent Expansion on Search Results (Nice-to-Have)

### The Need

Our artifact hierarchy is: **project → file (full content) → chunk (function/class, with embedding)**. Semantic search matches chunks, but the evaluator needs the full parent file for proper context. Currently, when search returns 8 matching chunks from 5 different files, we make 5 additional `GET /artifacts/{id}` calls to retrieve the parent files.

This N+1 pattern adds latency and complexity. The search step alone accounts for 9 HTTP calls (1 search + 8 parent lookups) per expectation, multiplied by 61 expectations = ~550 HTTP calls in the evaluation phase.

### Current Workaround

After search, we group matching chunks by `metadata.relative_path`, look up the file artifact ID from our in-memory `file_ids` map, and fetch each parent file individually.

### Proposed Enhancement

Add an optional `include_ancestors` or `expand_parent` flag to search results:

```json
{
  "query_vector": [...],
  "embedding_type": "nomic",
  "limit": 10,
  "include_parent": true
}
```

When enabled, each search result would include the parent artifact's content alongside the matching child:

```json
{
  "results": [
    {
      "artifact": { "id": "chunk-uuid", "content": "def foo()..." },
      "parent": { "id": "file-uuid", "content": "...full file..." },
      "score": 0.87
    }
  ]
}
```

This eliminates the N+1 pattern entirely. However, this is lower priority than scoped search and deletion — we can live with the extra calls.

---

## Priority Summary

| # | Enhancement | Priority | Impact |
|---|------------|----------|--------|
| 1 | Scoped semantic search (`parent_artifact_id` filter) | **Critical** | Eliminates cross-project contamination; makes multi-run/multi-project usage viable |
| 2 | Cascade artifact deletion (`DELETE /artifacts/{id}?cascade=true`) | **Critical** | Enables cleanup, idempotent re-runs, data lifecycle management |
| 3 | Parent expansion on search results (`include_parent` flag) | Nice-to-have | Reduces HTTP calls by ~5x in evaluation phase |

---

## Context: How Developer1 Uses Mimir

For reference, here is our current artifact hierarchy and data flow:

```
project-eval: localport (analysis)
├── src/localport/domain/entities/service.py (document, full content, NO embedding)
│   ├── service.py::module_header (document, chunk, WITH embedding)
│   ├── service.py::Service (document, chunk, WITH embedding)
│   └── service.py::ServiceFactory (document, chunk, WITH embedding)
├── src/localport/cli/app.py (document, full content, NO embedding)
│   ├── app.py::module_header (document, chunk, WITH embedding)
│   ├── app.py::create_app (document, chunk, WITH embedding)
│   └── ...
├── docs/design.md (document, full content, NO embedding)
│   ├── design.md::preamble (document, chunk, WITH embedding)
│   ├── design.md::Architecture (document, chunk, WITH embedding)
│   └── ...
├── "There should be a Service entity..." (finding, expectation)
├── "✅ There should be a Service entity..." (analysis, evaluation result)
└── ...
```

Search hits chunks → we need the parent file → we evaluate against full file content.

---

## 4. Unified Search Endpoint (HIGH PRIORITY)

### The Argument

Today Mimir has four search endpoints: fulltext, semantic, hybrid, and similar. We've documented that these endpoints have inconsistent filtering capabilities (graph scoping, pagination, metadata filtering are available on some but not others). We initially recommended making the filtering parameters consistent across all four.

But following that argument to its conclusion: **if the search type controls ranking and everything else should be identical, then four endpoints is the wrong abstraction.** Four endpoints that share 80% of their parameters is a code smell in an API just as it is in application code. The correct design is one endpoint where the ranking strategy is determined by what the consumer provides.

### What Actually Varies

| Current Endpoint | Unique Input | Shared Inputs |
|-----------------|-------------|---------------|
| Fulltext | Text query | Filtering, scoping, pagination, response format |
| Semantic | Embedding vector + type | Same |
| Hybrid | Text + vector + weight | Same |
| Similar | Artifact ID + embedding type | Same |

The unique part is **ranking input**. Everything else is identical.

### Proposed: `POST /search`

A single search endpoint where the **ranking strategy** is determined by which query parameters are provided:

```json
POST /search
{
  // --- Ranking (provide one or more to determine strategy) ---
  "query": "YamlConfigRepository",           // text → enables fulltext ranking
  "query_vector": [0.1, 0.2, ...],           // pre-computed vector → enables semantic ranking
  "embedding_type": "nomic",                 // which vector table to search against
  "semantic_weight": 0.4,                    // tune hybrid balance (when both query + vector provided)
  "similar_to": "artifact-uuid",             // artifact ID → use its stored vector for ranking
  
  // --- Filtering (always available, orthogonal to ranking) ---
  "artifact_types": ["document"],
  "metadata_filters": {
    "file_type": "python",
    "chunk_type": ["class", "function"]
  },
  
  // --- Scoping (always available, orthogonal to ranking) ---
  "scope": "project-artifact-uuid",          // graph-based: only artifacts connected to this one
  
  // --- Pagination (always available) ---
  "limit": 15,
  "offset": 0
}
```

The ranking strategy emerges from what the consumer provides:

| Consumer provides | Ranking behavior |
|------------------|-----------------|
| `query` only | Fulltext (PostgreSQL FTS) |
| `query_vector` + `embedding_type` | Semantic (cosine similarity against stored vectors) |
| `query` + `query_vector` | Hybrid (RRF fusion, tuned by `semantic_weight`) |
| `similar_to` + `embedding_type` | Similar (use artifact's existing embedding) |
| `similar_to` + `query` | Hybrid similar (re-rank similar results by text match) |

### Why One Endpoint

1. **Impossible to have inconsistent filtering.** One set of filters. They always work. No capability matrix to maintain.

2. **Progressive disclosure.** Start simple (`{"query": "foo"}`) and add capabilities as needed. No need to learn four endpoints and which supports what.

3. **Eliminates the "wrong endpoint" problem.** We spent hours debugging why semantic search wasn't scoped. The answer was "you picked the wrong endpoint." With one endpoint, there's no wrong choice.

4. **Composable ranking.** Want fulltext + similar? `{"query": "foo", "similar_to": "uuid"}`. Today you can't combine these at all.

5. **Simpler client code.** One `search()` method instead of four.

### Embedding Generation Is the Client's Job

Note the absence of `query_text` — the search endpoint does not generate embeddings. This is deliberate. Mimir's architecture is correct here:

- **`POST /embedding-types`** registers a vector schema (dimensions, distance metric). This is DDL, not data.
- **`POST /embeddings`** stores a pre-computed vector against an artifact.
- **`POST /search`** accepts a pre-computed query vector for ranking.

Mimir never calls Ollama, OpenAI, or any embedding provider. It stores and indexes vectors. Generation is the client's concern — the client chooses which model to use, manages licensing costs, and handles the Ollama/OpenAI call. This is the pgvector model: the database stores vectors, generation is external.

### Precedent

Elasticsearch uses a single `_search` endpoint with different query types in the body. Same principle: one door in, ranking determined by query shape, uniform filtering.

### Metadata Filtering Design

The `metadata_filters` parameter enables server-side filtering by arbitrary metadata fields stored on artifacts:

```json
{
  "metadata_filters": {
    "file_type": "python",
    "chunk_type": ["class", "function"]
  }
}
```

- Array values mean "any of" (OR): `chunk_type` matches `"class"` OR `"function"`
- Multiple keys mean "all of" (AND): must be `file_type=python` AND one of the chunk types
- Server-side filtering is essential for correct pagination — client-side post-filtering breaks `limit`/`offset`

### Graph Scoping vs. Graph Queries

There are two distinct graph concerns that shouldn't be conflated:

**1. Scoping (part of search)** — "Restrict search candidates to a subgraph." This is a WHERE clause on the candidate set. It belongs in the unified search endpoint because it's filtering, not ranking.

**2. Graph traversal** — "Starting from artifact X, follow relation Y, then search those targets." This is a multi-hop query that combines traversal with search. It may be better served by separate graph query endpoints.

#### Scoping in Search

For search scoping, the consumer needs to specify:

- **Anchor artifact** — which artifact to scope from
- **Relation types** — which edges to follow (e.g., only `parent_of`, only `supports`, or any)
- **Direction** — incoming edges, outgoing edges, or both
- **Depth** — direct connections only (1 hop) or recursive (descendants)

Mimir's existing `related_to` parameter on fulltext/hybrid already supports anchor + relation type + direction. What's missing is:
- Availability on all search types (semantic, similar)
- Depth control (especially for parent/child hierarchies where we want all descendants)

For our use case, the common scoping pattern is "search only among descendants of this project artifact" — which requires following `parent_of` edges recursively (project → files → chunks). A simpler pattern is "search only among artifacts directly related to this artifact via `supports` relations."

#### Graph Queries (Separate API?)

Multi-hop traversal ("find artifacts that X supports, then find what those artifacts reference, then search among those") is a different problem. It's closer to a graph query language than a search filter.

Options the Mimir team should consider:

1. **Keep it simple**: Only support single-hop scoping in search (anchor + relation type + direction). Multi-hop queries are composed client-side via multiple API calls — first traverse, then search within the traversed set.

2. **Add a graph query endpoint**: `POST /graph/traverse` that returns artifact IDs for a given traversal pattern. The result can then be fed into search as a scoping set.

3. **Support recursive depth in scoping**: Allow `depth: "recursive"` or `depth: 2` in the search scope to follow edges transitively. This covers the parent/child hierarchy case (our most common need) without requiring a full graph query language.

We'd recommend option 3 for the search endpoint (covers 90% of use cases including ours), with option 2 as a future addition if consumers need complex traversals.

#### What we need now

For code evaluation, our graph scoping needs are:

| Use Case | Anchor | Relations | Direction | Depth |
|----------|--------|-----------|-----------|-------|
| "Only this project's files" | Project artifact | parent_of | Children | Recursive (2 hops: project → file → chunk) |
| "Code that this evaluation examined" | Evaluation artifact | supports | Outgoing | 1 hop |
| "All evaluations for this expectation" | Expectation artifact | references | Incoming | 1 hop |

The first case (recursive descendants) is the critical one. The others are single-hop and simpler.

---

### Updated Priority Summary

| # | Enhancement | Priority | Status |
|---|------------|----------|--------|
| 1 | **Cascade artifact deletion** | **Critical** | No workaround exists |
| 2 | **Unified search endpoint** (`POST /search`) | **High** | Replaces 4 inconsistent endpoints; structurally prevents filtering gaps |
| 3 | **Metadata filtering** on search | **High** | Part of unified search; eliminates client-side post-filtering |
| 4 | **Graph scoping** on search | **High** | Part of unified search; critical for multi-project use |
| 5 | **Pagination** on all ranking types | Medium | Part of unified search; currently only fulltext has it |
| 6 | Parent expansion on search results | Low (deferred) | Solved client-side via contextual chunk metadata |
