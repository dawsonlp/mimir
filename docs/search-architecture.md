# Mímir V3 Search Architecture

**Last Updated**: 2026-02-13 (v3.0.0)

---

## Overview

Mímir provides four search strategies — fulltext, semantic, hybrid, and similar — all accessed through a single unified endpoint (`POST /search`). The ranking strategy is automatically inferred from which parameters the consumer provides. All strategies share the same filtering, pagination, and scoping capabilities.

---

## Unified Endpoint: `POST /search`

All search goes through one endpoint. The ranking strategy is inferred from the request body:

| Parameters Provided | Inferred Strategy | `embedding_type` Required? |
|--------------------|-------------------|---------------------------|
| `query` only | **Fulltext** | No |
| `query_vector` + `embedding_type` | **Semantic** | Yes |
| `query` + `query_vector` + `embedding_type` | **Hybrid** (RRF) | Yes |
| `similar_to` + `embedding_type` | **Similar** | Yes |
| None of the above | **Error 422** | — |
| `query_vector` + `similar_to` | **Error 422** (ambiguous) | — |
| `query` + `similar_to` | **Error 422** (reserved for future) | — |

The response includes a `strategy` field indicating which ranking algorithm was used.

### Error Handling

Invalid parameter combinations return 422 with a structured error (`code` + `detail` message explaining what was inferred and why). See [Unified Search Technical Design §5](unified-search-technical-design.md) for the complete error message table.

---

## Search Strategies

### 1. Fulltext Search

Uses PostgreSQL native full-text search capabilities.

**Mechanism**: `tsvector`/`tsquery` with GIN index, ranked by `ts_rank`

**When to use**: Text keyword matching, exact phrase search, when no embeddings are available

**Strengths**:
- Fast exact phrase matching
- Handles stemming and stop words
- No external API calls needed
- Supports Boolean operators (AND, OR, NOT)

**Weaknesses**:
- Misses semantic similarity (synonyms, paraphrases)
- Language-specific stemming
- No concept of meaning

**Example**:
```json
POST /search
{"query": "python programming guide", "limit": 10}
```

---

### 2. Semantic Search

Uses vector similarity via the pgvector extension.

**Mechanism**: Cosine distance between query embedding and stored embeddings

**Index**: HNSW (Hierarchical Navigable Small World) for approximate nearest neighbor

**When to use**: Finding conceptually similar content, cross-language matching, when you have a pre-computed embedding vector

**Strengths**:
- Finds conceptually similar content
- Works across synonyms and paraphrases
- Quality depends on embedding model choice

**Weaknesses**:
- May miss exact keyword matches
- Requires embedding generation (external API or local model)
- Quality varies by embedding model

**Parameters**:
- `query_vector` — Pre-computed embedding vector (Mimir does not generate embeddings server-side)
- `embedding_type` — Which embedding type to search against (determines the vector table)
- `similarity_threshold` — Minimum cosine similarity score (0.0–1.0, default 0.0)

**Example**:
```json
POST /search
{
  "query_vector": [0.1, 0.2, ...],
  "embedding_type": "nomic-embed-text",
  "similarity_threshold": 0.7,
  "limit": 10
}
```

---

### 3. Hybrid Search (Reciprocal Rank Fusion)

Combines semantic and fulltext results using Reciprocal Rank Fusion (RRF).

**When to use**: Best overall relevance — combines keyword precision with semantic understanding

**Why RRF?**

Semantic and fulltext search return incomparable scores:
- Semantic: cosine similarity (0.0 to 1.0)
- Fulltext: `ts_rank` values (arbitrary positive numbers)

RRF solves this by using **rank positions** instead of raw scores.

**RRF Formula**:

For each document, sum contributions from each result list:

```
RRF_score = Σ (1 / (k + rank))
```

Where:
- `k` = 60 (constant, configurable via `rrf_k`)
- `rank` = position in each result list (1, 2, 3...)

**Example**:

A document ranking #2 in semantic and #5 in fulltext:
- Semantic contribution: 1/(60+2) = 0.0161
- Fulltext contribution: 1/(60+5) = 0.0154
- Combined RRF score: 0.0315

This beats a document ranking #1 in only one method (0.0164).

**Key insight**: Documents appearing in both result sets get boosted — being relevant by multiple criteria indicates higher overall relevance.

**Tuning Parameters**:
- `semantic_weight` — Balance between fulltext (0.0) and semantic (1.0), default 0.5
- `rrf_k` — RRF constant, default 60. Lower values increase the weight of top-ranked results.

**Example**:
```json
POST /search
{
  "query": "python programming",
  "query_vector": [0.1, 0.2, ...],
  "embedding_type": "nomic-embed-text",
  "semantic_weight": 0.7,
  "rrf_k": 60,
  "limit": 10
}
```

---

### 4. Similar Artifact Search

Finds artifacts similar to an existing artifact by comparing its embedding to all other embeddings of the same type.

**When to use**: "More like this" functionality, finding related content from a known artifact

**Mechanism**: Looks up the embedding for the given artifact, then performs cosine similarity search against all other artifacts' embeddings of the same type.

**Parameters**:
- `similar_to` — UUID of the artifact to find similar items for
- `embedding_type` — Which embedding type to use for comparison
- `similarity_threshold` — Minimum similarity score (optional)

**Example**:
```json
POST /search
{
  "similar_to": "550e8400-e29b-41d4-a716-446655440000",
  "embedding_type": "nomic-embed-text",
  "similarity_threshold": 0.5,
  "limit": 10
}
```

**Note**: If the artifact has no embedding of the specified type, the endpoint returns empty results (not an error).

---

## Filtering Capabilities

All filters work uniformly across all four search strategies.

### Artifact Type Filter (`artifact_types`)

Restrict results to specific artifact types (e.g., `document`, `chunk`, `note`).

```json
{"query": "test", "artifact_types": ["document", "chunk"]}
```

### Metadata Filtering (`metadata_filters`)

Filter by artifact JSONB metadata fields. Uses AND across keys, OR within array values.

```json
{"query": "test", "metadata_filters": {"language": "python"}}
```

```json
{"query": "test", "metadata_filters": {"language": ["python", "rust"], "source": "import"}}
```

The above matches artifacts where `language` is "python" OR "rust", AND `source` is "import".

**Implementation**: Uses PostgreSQL JSONB `@>` containment operator, leveraging GIN indexes for performance.

**Limitations**:
- No negation (`NOT`) — reserved for future extension via object wrapper (e.g., `{"not": "value"}`)
- No range queries on metadata values
- No nested metadata object filtering

### Parent-Child Hierarchy Scoping (`scope_artifact_id`)

Restrict results to descendants of a specific artifact in the parent-child hierarchy. Uses a recursive CTE on `parent_artifact_id` to resolve the full descendant tree.

```json
{"query": "test", "scope_artifact_id": "project-uuid-here"}
```

**Behavior**:
- Includes all descendants at any depth (not just direct children)
- If the scope artifact is soft-deleted, returns empty results (scope anchor must be active)
- Soft-deleted intermediate nodes break the chain — their children are unreachable via scoping
- Recursive CTE includes `AND tenant_id = %s` at every level (multi-tenant safety)
- Recursive CTE excludes soft-deleted nodes (`deleted_at IS NULL`)

**Performance**: Median 1.16ms, p95 1.34ms for a 200-artifact, 3-level hierarchy.

### Relation Filtering (`related_to`)

Filter results to artifacts that have a relation to a specific artifact.

```json
{
  "query": "test",
  "related_to": "artifact-uuid",
  "relation_type": "references",
  "relation_direction": "outgoing"
}
```

**Parameters**:
- `related_to` — UUID of the artifact to check relations against
- `relation_type` — Optional: filter by relation type name (e.g., `references`, `child_of`)
- `relation_direction` — `incoming`, `outgoing`, or `both` (default: `both`)

**Implementation**: Post-filtering — the search executes with 3× the requested limit, then filters results against the relation set, then trims to the requested limit. This ensures sufficient results survive the filter.

---

## Pagination

All strategies support `limit` and `offset` pagination.

```json
{"query": "test", "limit": 20, "offset": 40}
```

- `limit` — Maximum results to return (1–100, default 20)
- `offset` — Number of results to skip (default 0)

**Performance note**: Deep offsets degrade on HNSW indexes because pgvector must scan past skipped results. For most use cases, offset < 200 performs well. For deep pagination, consider using `scope_artifact_id` or `metadata_filters` to narrow the result set first.

---

## Soft-Delete Interaction

Search automatically excludes soft-deleted artifacts:

- All search queries include `WHERE a.deleted_at IS NULL`
- Embeddings of soft-deleted artifacts do NOT participate in semantic/vector search
- Relations where source OR target is soft-deleted are excluded from relation queries
- `scope_artifact_id` pointing to a soft-deleted artifact returns empty results

See [Soft-Delete Semantics](soft-delete-semantics.md) for the complete specification.

---

## Embedding Architecture

### Design Principle: Server Does Not Generate Embeddings

Mimir stores and searches embeddings but does **not** generate them server-side. Clients are responsible for:
1. Choosing an embedding model
2. Generating vectors via their preferred provider
3. Storing vectors via `POST /embeddings`
4. Providing `query_vector` when searching

This keeps Mimir model-agnostic and avoids coupling to specific embedding providers.

### Embedding Types

Each embedding type registers with a `code`, `provider`, and `dimensions`. This creates a dedicated vector table (`vec_{code}`) with the correct dimensionality.

### Supported Providers (Client-Side)

| Provider | Environment Variable | Best For |
|----------|---------------------|----------|
| Voyage AI | VOYAGE_API_KEY | Production (Anthropic recommended) |
| OpenAI | OPENAI_API_KEY | General purpose |
| Ollama | OLLAMA_BASE_URL | Local/offline |

### Model Examples

| Provider | Models | Dimensions |
|----------|--------|------------|
| Voyage AI | voyage-3, voyage-3-large, voyage-code-3 | 1024 |
| OpenAI | text-embedding-3-small, text-embedding-3-large | 1536, 3072 |
| Ollama | nomic-embed-text, all-minilm, mxbai-embed-large | 768, 384, 1024 |

---

## Chunking Strategy

**Key Design Decision**: Chunking is the responsibility of import clients, not the storage layer.

**Rationale**:
- Different content types require different chunking strategies (code, markdown, conversations, legal documents)
- Domain expertise belongs in client applications
- Storage layer stays ontology-agnostic

**Pattern**:
1. Client imports parent document as artifact (type: `document`)
2. Client creates chunk artifacts (type: `chunk`) with `parent_artifact_id` pointing to the document
3. Client creates embeddings for chunks
4. Search can be scoped to a project or document using `scope_artifact_id`

**Context Expansion**:
When search returns a chunk, clients can:
1. Retrieve parent via `parent_artifact_id`
2. Retrieve sibling chunks via the parent's children
3. Use the context service (`GET /context/{artifact_id}`) for assembled context with relation traversal

---

## Performance Considerations

### Indexes

| Type | Purpose | Used By |
|------|---------|---------|
| HNSW | Approximate nearest neighbor for vectors | Semantic, hybrid, similar |
| GIN (tsvector) | Full-text search token lookup | Fulltext, hybrid |
| GIN (JSONB) | Metadata containment queries | `metadata_filters` |
| B-tree | Filtering columns | `tenant_id`, `artifact_type`, `created_at`, `deleted_at` |

### Query Optimization

- All queries include `tenant_id` filter (uses B-tree index)
- All queries include `deleted_at IS NULL` filter (uses partial index)
- Semantic search uses HNSW index for sub-linear search time
- Fulltext search leverages GIN index for fast token lookup
- Hybrid search runs both queries, then fuses results with RRF
- Metadata filtering uses GIN index on JSONB `metadata` column
- Hierarchy scoping uses recursive CTE with indexed `parent_artifact_id` lookups

### Known Limitations

- Deep offset pagination (offset > 200) degrades on HNSW indexes
- Relation filtering is post-filter, not pre-filter — may return fewer results than `limit` if few matches survive
- No cross-embedding-type search — each search targets exactly one embedding type

---

## Deprecated Endpoint

| Endpoint | Status | Sunset Date | Replacement |
|----------|--------|-------------|-------------|
| `GET /search/fulltext` | Deprecated (returns `Deprecation: true` header) | 2026-08-01 | `POST /search` with `query` |

Legacy endpoints `POST /search/semantic`, `POST /search/hybrid`, and `GET /search/similar/{id}` were removed in v3.0.0.

---

## Related Documentation

- [Unified Search Technical Design](unified-search-technical-design.md) — Implementation details and design decisions
- [Enhancement Roadmap](archive/enhancement-roadmap-checklist.md) — Phase tracking for search enhancements (archived — see [roadmap.md](roadmap.md))
- [Soft-Delete Semantics](soft-delete-semantics.md) — How deletion interacts with search
- [Migration Guide](../comms/06_v3_migration_guide.md) — Consumer migration from legacy endpoints

---

## Changelog

| Date | Change |
|------|--------|
| 2026-02-13 | Initial architecture document |
| 2026-02-13 | V3.0.0 rewrite: unified endpoint, four strategies, all filtering/pagination/scoping/soft-delete documented |