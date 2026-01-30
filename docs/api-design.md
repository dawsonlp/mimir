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

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /embeddings | Create embedding for artifact |
| GET | /embeddings | List embeddings (filterable) |
| GET | /embeddings/{id} | Get embedding by UUID |
| GET | /embeddings/artifact/{id} | Get all embeddings for artifact |
| GET | /embeddings/providers | List available embedding providers and models |

**Not supported:**
- ~~DELETE /embeddings/{id}~~ — No deletes

### Query Parameters

| Parameter | Description |
|-----------|-------------|
| artifact_id | Filter by artifact |
| model | Filter by model name |
| limit, offset | Pagination |

---

## Search

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /search | Unified search (semantic, fulltext, or hybrid) |
| POST | /search/semantic | Vector similarity search only |
| POST | /search/fulltext | PostgreSQL full-text search only |
| POST | /search/similar | Find artifacts similar to a given artifact |

**Request Fields:**
- query: Search query text
- search_type: semantic, fulltext, or hybrid
- model: Embedding model (for semantic search)
- limit, offset: Pagination
- artifact_types: Filter by artifact types
- min_similarity: Minimum similarity threshold
- include_content: Include full content in results

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
