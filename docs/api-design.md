# Mímir V2 API Design

## Base URL

All endpoints are prefixed with `/api/v1`.

## Authentication

Tenant context is required via `X-Tenant-ID` header on all entity endpoints.

## Core Principles

| Principle | API Behavior |
|-----------|--------------|
| **Client-generated UUIDs** | POST accepts optional `id` field (UUIDv7); server generates if omitted |
| **Append-only** | No PATCH/PUT on content tables |
| **No deletes** | No DELETE on content tables (for now) |
| **Idempotency** | Same UUID twice returns 409 Conflict |
| **Admin tables mutable** | Tenants and vocabulary tables support full CRUD |

---

## Tenants (Admin - Mutable)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /tenants | Create tenant |
| GET | /tenants | List tenants (paginated) |
| GET | /tenants/{id} | Get tenant by ID |
| PATCH | /tenants/{id} | Update tenant |
| DELETE | /tenants/{id} | Delete tenant |

---

## Vocabulary Tables (Admin - Mutable)

### Artifact Types

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /artifact-types | Create artifact type |
| GET | /artifact-types | List artifact types |
| GET | /artifact-types/{code} | Get artifact type by code |
| PATCH | /artifact-types/{code} | Update artifact type |
| DELETE | /artifact-types/{code} | Delete artifact type |

### Relation Types

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /relation-types | Create relation type |
| GET | /relation-types | List relation types |
| GET | /relation-types/{code} | Get relation type by code |
| PATCH | /relation-types/{code} | Update relation type |
| DELETE | /relation-types/{code} | Delete relation type |

### Embedding Types

Embedding types define embedding models and their vector dimensions. Creating an embedding type automatically creates a dedicated vector table with HNSW index in the `mimir_vectors` schema.

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /embedding-types | Create embedding type (creates vector table) |
| GET | /embedding-types | List embedding types |
| GET | /embedding-types/{code} | Get embedding type by code |
| DELETE | /embedding-types/{code} | Deactivate embedding type (soft delete) |

**Create Embedding Type:**

```json
{
  "code": "nomic-embed-text",
  "display_name": "Nomic Embed Text",
  "provider": "ollama",
  "dimensions": 768,
  "distance_metric": "cosine",
  "max_tokens": 8192,
  "description": "Good balance of quality and speed for RAG"
}
```

**Code Validation:** Codes must be 3-50 characters, lowercase alphanumeric with hyphens, starting with a letter. Pattern: `^[a-z][a-z0-9-]{2,49}$`

**What Happens on Create:**
1. Creates row in `mimirdata.embedding_type` vocabulary table
2. Creates `mimir_vectors.vec_{sanitized_code}` vector table
3. Creates HNSW index for efficient similarity search

---

## Artifacts (Append-Only)

All content types share the same endpoints. Type discrimination via `artifact_type`.

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /artifacts | Create artifact (optional client UUID) |
| GET | /artifacts | List artifacts (paginated, filterable) |
| GET | /artifacts/{id} | Get artifact by UUID |
| GET | /artifacts/{id}/children | Get child artifacts (positional types) |
| GET | /artifacts/{id}/related | Get related artifacts via relations |

**Not supported:**
- ~~PATCH /artifacts/{id}~~ — No updates
- ~~DELETE /artifacts/{id}~~ — No deletes
- ~~GET /artifacts/{id}/versions~~ — No version concept

### Create Artifact

**Request:**
```json
{
  "id": "01926a5c-8b4e-7d3f-9e1a-2c4d6e8f0a1b",  // Optional UUIDv7
  "artifact_type": "decision",
  "title": "Use PostgreSQL",
  "content": "We decided to use PostgreSQL because...",
  "parent_artifact_id": null,
  "start_offset": null,
  "end_offset": null,
  "position_metadata": null,
  "source": "manual",
  "source_system": null,
  "external_id": null,
  "metadata": {
    "confidence": 0.95,
    "status": "active"
  }
}
```

**Response (201 Created):**
```json
{
  "id": "01926a5c-8b4e-7d3f-9e1a-2c4d6e8f0a1b",
  "tenant_id": 1,
  "artifact_type": "decision",
  "title": "Use PostgreSQL",
  "content": "We decided to use PostgreSQL because...",
  "content_hash": "a1b2c3d4e5f6...",
  "created_at": "2026-01-12T05:49:00Z",
  "metadata": {...}
}
```

**Response (409 Conflict)** — If same UUID exists:
```json
{
  "detail": "Artifact with this ID already exists",
  "existing_id": "01926a5c-8b4e-7d3f-9e1a-2c4d6e8f0a1b"
}
```

### Query Parameters

| Parameter | Description |
|-----------|-------------|
| artifact_type | Filter by type |
| source | Filter by source |
| source_system | Filter by source system |
| parent_artifact_id | Filter by parent (for positional types) |
| content_hash | Find by content hash |
| external_id | Find by external ID (with source_system) |
| limit, offset | Pagination |

---

## Relations (Append-Only)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /relations | Create relation (optional client UUID) |
| GET | /relations | List relations (filterable) |
| GET | /relations/{id} | Get relation by UUID |
| GET | /relations/artifact/{id} | Get all relations for an artifact |

**Not supported:**
- ~~PATCH /relations/{id}~~ — No updates
- ~~DELETE /relations/{id}~~ — No deletes

### Create Relation

**Request:**
```json
{
  "id": "01926a5c-9999-7d3f-9e1a-000000000001",  // Optional UUIDv7
  "source_id": "01926a5c-8b4e-7d3f-9e1a-2c4d6e8f0a1b",
  "target_id": "01926a5c-8b4e-7d3f-9e1a-2c4d6e8f0a2c",
  "relation_type": "supersedes",
  "confidence": 1.0,
  "metadata": {}
}
```

**Response (201 Created):**
```json
{
  "id": "01926a5c-9999-7d3f-9e1a-000000000001",
  "tenant_id": 1,
  "source_id": "...",
  "target_id": "...",
  "relation_type": "supersedes",
  "confidence": 1.0,
  "created_at": "2026-01-12T05:49:00Z",
  "metadata": {}
}
```

### Query Parameters

| Parameter | Description |
|-----------|-------------|
| source_id | Filter by source artifact |
| target_id | Filter by target artifact |
| relation_type | Filter by relation type |
| limit, offset | Pagination |

---

## Embeddings (Append-Only)

Embeddings use a multi-table architecture where each embedding type has its own vector table with proper HNSW indexing. See `docs/embedding-architecture-design.md` for full details.

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /embeddings | Create embedding for artifact |
| GET | /embeddings | List embeddings (filterable) |
| GET | /embeddings/{id} | Get embedding by UUID |
| GET | /embeddings/artifact/{id} | Get all embeddings for artifact |
| POST | /embeddings/similar | Find similar embeddings by vector |

**Not supported:**
- ~~DELETE /embeddings/{id}~~ — No deletes

### Create Embedding

**Prerequisites:** The `embedding_type` must be registered first via `POST /embedding-types`.

**Request:**
```json
{
  "artifact_id": "01926a5c-8b4e-7d3f-9e1a-2c4d6e8f0a1b",
  "embedding_type": "nomic-embed-text",
  "embedding": [0.1, 0.2, ...],  // Must match type's dimensions
  "metadata": {}
}
```

**Response (201 Created):**
```json
{
  "id": "01926a5c-9999-7d3f-9e1a-000000000001",
  "tenant_id": 1,
  "artifact_id": "01926a5c-8b4e-7d3f-9e1a-2c4d6e8f0a1b",
  "embedding_type": "nomic-embed-text",
  "created_at": "2026-01-12T05:49:00Z",
  "metadata": {}
}
```

**Response (400 Bad Request)** — If dimensions don't match:
```json
{
  "detail": "Embedding dimensions mismatch: nomic-embed-text expects 768, got 1536"
}
```

### Similarity Search

**Endpoint:** `POST /embeddings/similar`

Searches the vector table for the specified embedding type using HNSW index.

**Request:**
```json
{
  "query_vector": [0.1, 0.2, ...],
  "embedding_type": "nomic-embed-text",
  "limit": 20,
  "similarity_threshold": 0.7,
  "artifact_types": ["decision", "finding"]
}
```

**Response:**
```json
{
  "results": [
    {
      "embedding_id": "...",
      "artifact_id": "...",
      "embedding_type": "nomic-embed-text",
      "similarity": 0.92
    }
  ],
  "total": 15
}
```

**Note:** You cannot search across different embedding types because they have different dimensions.

### Query Parameters

| Parameter | Description |
|-----------|-------------|
| artifact_id | Filter by artifact UUID |
| embedding_type | Filter by embedding type code |
| limit, offset | Pagination |

---

## Search

Mímir provides three search modes plus similarity search and relation-aware filtering.

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /search/fulltext | PostgreSQL full-text search |
| POST | /search/semantic | Vector similarity search |
| POST | /search/hybrid | Combined fulltext + semantic with RRF ranking |
| GET | /search/similar/{artifact_id} | Find artifacts similar to a given artifact |

### Full-Text Search

**Endpoint:** `GET /search/fulltext?query={text}`

Uses PostgreSQL's built-in full-text search with ranking.

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `query` | string | required | Search text |
| `artifact_types` | string[] | null | Filter by artifact types |
| `limit` | int | 20 | Max results (1-100) |
| `offset` | int | 0 | Pagination offset |
| `related_to` | UUID | null | Filter to artifacts related to this artifact |
| `relation_type` | string | null | Filter by relation type (requires `related_to`) |
| `relation_direction` | string | `both` | `incoming`, `outgoing`, or `both` |

**Example:**
```bash
# Basic fulltext search
curl -X GET "http://localhost:38000/search/fulltext?query=PostgreSQL" \
  -H "X-Tenant-ID: 1"

# Search with artifact type filter
curl -X GET "http://localhost:38000/search/fulltext?query=security&artifact_types=decision&artifact_types=finding" \
  -H "X-Tenant-ID: 1"
```

### Semantic Search

**Endpoint:** `POST /search/semantic`

Uses vector similarity (cosine distance) against pre-computed embeddings.

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `artifact_types` | string[] | null | Filter by artifact types |
| `limit` | int | 20 | Max results (1-100) |
| `similarity_threshold` | float | 0.0 | Minimum similarity (0.0-1.0) |
| `model` | string | null | Embedding model to use |
| `related_to` | UUID | null | Filter to artifacts related to this artifact |
| `relation_type` | string | null | Filter by relation type (requires `related_to`) |
| `relation_direction` | string | `both` | `incoming`, `outgoing`, or `both` |

**Request Body:** List of floats representing the query embedding vector

**Example:**
```bash
# Semantic search with pre-computed query embedding
curl -X POST "http://localhost:38000/search/semantic?limit=10" \
  -H "X-Tenant-ID: 1" \
  -H "Content-Type: application/json" \
  -d '[0.1, 0.2, 0.3, ...]'  # 1536-dimensional vector for OpenAI embeddings
```

### Hybrid Search

**Endpoint:** `POST /search/hybrid?query={text}`

Combines fulltext and semantic search using Reciprocal Rank Fusion (RRF).

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `query` | string | required | Search text |
| `artifact_types` | string[] | null | Filter by artifact types |
| `limit` | int | 20 | Max results (1-100) |
| `rrf_k` | int | 60 | RRF constant (higher = less aggressive ranking) |
| `semantic_weight` | float | 0.5 | Weight for semantic scores (0.0-1.0) |
| `model` | string | null | Embedding model to use |
| `related_to` | UUID | null | Filter to artifacts related to this artifact |
| `relation_type` | string | null | Filter by relation type (requires `related_to`) |
| `relation_direction` | string | `both` | `incoming`, `outgoing`, or `both` |

**Request Body:** List of floats representing the query embedding vector

**Example:**
```bash
# Hybrid search with 70% weight on semantic
curl -X POST "http://localhost:38000/search/hybrid?query=database%20performance&semantic_weight=0.7" \
  -H "X-Tenant-ID: 1" \
  -H "Content-Type: application/json" \
  -d '[0.1, 0.2, 0.3, ...]'
```

### Similarity Search

**Endpoint:** `GET /search/similar/{artifact_id}`

Find artifacts similar to a given artifact using its embedding.

**Path Parameters:**
- `artifact_id`: UUID of the source artifact

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `limit` | int | 10 | Max results (1-50) |
| `artifact_types` | string[] | null | Filter by artifact types |
| `model` | string | null | Embedding model to use |

### Relation-Aware Search Filters

All search endpoints support filtering results based on relationship structure. This is powerful for queries like:
- "Find all summaries derived from this document"
- "Find notes that reference this decision"
- "Find decisions related to this analysis"

**Parameters:**

| Parameter | Description |
|-----------|-------------|
| `related_to` | UUID of the anchor artifact. Only return artifacts that have a relation to/from this artifact. |
| `relation_type` | Filter by specific relation type (e.g., `derived_from`, `supports`, `references`). Requires `related_to`. |
| `relation_direction` | Which direction to check: `incoming` (others → anchor), `outgoing` (anchor → others), or `both`. |

**How Directions Work:**

Given a relation: `source_id → target_id`

| Direction | Anchor Position | Returns |
|-----------|-----------------|---------|
| `outgoing` | Anchor is `source_id` | Artifacts that anchor points TO |
| `incoming` | Anchor is `target_id` | Artifacts that point TO anchor |
| `both` | Either position | All related artifacts |

**Examples:**

```bash
# Find all artifacts related to a specific document
curl -X GET "http://localhost:38000/search/fulltext?query=PostgreSQL&related_to=01926a5c-0001-7000-8000-000000000001" \
  -H "X-Tenant-ID: 1"

# Find only artifacts derived FROM this document (incoming relations where doc is target)
curl -X GET "http://localhost:38000/search/fulltext?query=PostgreSQL&related_to=01926a5c-0001-7000-8000-000000000001&relation_direction=incoming" \
  -H "X-Tenant-ID: 1"

# Find only summaries derived from this document
curl -X GET "http://localhost:38000/search/fulltext?query=PostgreSQL&related_to=01926a5c-0001-7000-8000-000000000001&relation_type=derived_from&artifact_types=summary" \
  -H "X-Tenant-ID: 1"

# Semantic search filtered by relation
curl -X POST "http://localhost:38000/search/semantic?related_to=01926a5c-0001-7000-8000-000000000001&relation_type=supports" \
  -H "X-Tenant-ID: 1" \
  -H "Content-Type: application/json" \
  -d '[0.1, 0.2, 0.3, ...]'
```

**Important Notes:**
- Relation filters are applied **post-search**, meaning search scoring/ranking is computed first, then filtered
- This preserves the relevance order of results
- If `relation_type` is specified without `related_to`, it is ignored
- The anchor artifact itself is not included in results

### Search Response

All search endpoints return the same response structure:

```json
{
  "results": [
    {
      "artifact": {
        "id": "01926a5c-8b4e-7d3f-9e1a-2c4d6e8f0a1b",
        "tenant_id": 1,
        "artifact_type": "decision",
        "title": "Use PostgreSQL",
        "content": "We decided to use PostgreSQL because...",
        "created_at": "2026-01-12T05:49:00Z",
        "metadata": {...}
      },
      "score": 0.85,
      "rank": 1
    },
    ...
  ],
  "total": 15,
  "query": "PostgreSQL"
}
```

| Field | Description |
|-------|-------------|
| `results[].artifact` | The matched artifact |
| `results[].score` | Relevance score (interpretation varies by search type) |
| `results[].rank` | Position in results (1-indexed) |
| `total` | Total matching artifacts (for pagination) |
| `query` | The search query used |

---

## Provenance (Append-Only)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /provenance | List events (filterable) |
| GET | /provenance/artifact/{id} | Get history for artifact |

**Not supported:**
- ~~POST /provenance~~ — Events are created automatically on artifact/relation creates

### Query Parameters

| Parameter | Description |
|-----------|-------------|
| entity_type | Filter by entity type (artifact, relation, embedding) |
| entity_id | Filter by entity UUID |
| action | Filter by action type |
| actor_type | Filter by actor type |
| actor_id | Filter by actor ID |
| after, before | Time range |
| limit, offset | Pagination |

---

## Common Response Patterns

### Pagination

All list endpoints return paginated responses:
```json
{
  "items": [...],
  "total": 150,
  "limit": 50,
  "offset": 0
}
```

### Error Responses

| Status | Meaning |
|--------|---------|
| 400 | Bad request (validation error) |
| 404 | Resource not found |
| 409 | Conflict (duplicate UUID, constraint violation) |
| 422 | Unprocessable entity (invalid data) |
| 500 | Internal server error |

### Headers

| Header | Description |
|--------|-------------|
| X-Tenant-ID | Required tenant context (integer) |

---

## What Changed from V1

| V1 | V2 |
|----|----|
| PATCH /artifacts/{id} | Removed |
| DELETE /artifacts/{id} | Removed |
| GET /artifacts/{id}/versions | Removed |
| GET /artifacts/{id}/versions/{version} | Removed |
| PATCH /relations/{id} | Removed |
| DELETE /relations/{id} | Removed |
| DELETE /embeddings/{id} | Removed |
| All /spans endpoints | Removed (spans are positional artifacts) |
| POST /provenance | Removed (auto-created) |
| Integer IDs in requests | UUID (UUIDv7) |
| Server generates all IDs | Client can provide UUID |
