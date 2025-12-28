# Mímir V2 API Design

## Base URL

All endpoints are prefixed with `/api/v1`.

## Authentication

Tenant context is required via `X-Tenant-ID` header on all entity endpoints.

---

## Tenants

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /tenants | Create tenant |
| GET | /tenants | List tenants (paginated) |
| GET | /tenants/{id} | Get tenant by ID |
| PATCH | /tenants/{id} | Update tenant |
| DELETE | /tenants/{id} | Delete tenant |

---

## Artifacts

All content types (conversation, document, note, chunk, intent, decision, analysis, etc.) share the same endpoints.

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /artifacts | Create artifact |
| GET | /artifacts | List artifacts (paginated, filterable) |
| GET | /artifacts/{id} | Get artifact by ID |
| PATCH | /artifacts/{id} | Update artifact |
| DELETE | /artifacts/{id} | Delete artifact |
| GET | /artifacts/{id}/versions | List artifact versions |
| GET | /artifacts/{id}/versions/{version} | Get specific version |
| GET | /artifacts/types | List valid artifact types |

**Query Parameters:**
- artifact_type: Filter by type
- source: Filter by source
- source_system: Filter by source system
- limit, offset: Pagination

---

## Relations

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /relations | Create relation |
| GET | /relations | List relations (filterable) |
| GET | /relations/{id} | Get relation by ID |
| PATCH | /relations/{id} | Update relation |
| DELETE | /relations/{id} | Delete relation |
| GET | /relations/entity/{type}/{id} | Get all relations for an entity |

**Query Parameters:**
- source_type, source_id: Filter by source entity
- target_type, target_id: Filter by target entity
- relation_type: Filter by relation type

---

## Spans

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /spans | Create span |
| GET | /spans | List spans (filterable) |
| GET | /spans/{id} | Get span by ID |
| PATCH | /spans/{id} | Update span |
| DELETE | /spans/{id} | Delete span |

**Query Parameters:**
- artifact_id: Filter by artifact
- span_type: Filter by type

---

## Embeddings

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /embeddings | Create embedding for artifact |
| GET | /embeddings | List embeddings (filterable) |
| GET | /embeddings/{id} | Get embedding by ID |
| DELETE | /embeddings/{id} | Delete embedding |
| DELETE | /embeddings/artifact/{id} | Delete all embeddings for artifact |
| GET | /embeddings/providers | List available embedding providers and models |

**Query Parameters:**
- artifact_id: Filter by artifact
- model: Filter by model name

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

## Provenance

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /provenance | Record provenance event |
| GET | /provenance | List events (filterable) |
| GET | /provenance/entity/{type}/{id} | Get history for entity |
| GET | /provenance/correlation/{id} | Get correlated events |

**Query Parameters:**
- entity_type, entity_id: Filter by entity
- action: Filter by action type
- actor_type, actor_id: Filter by actor
- after, before: Time range

---

## Common Response Patterns

### Pagination

All list endpoints return paginated responses with:
- items: Array of results
- total: Total count
- limit: Page size
- offset: Current offset

### Error Responses

| Status | Meaning |
|--------|---------|
| 400 | Bad request (validation error) |
| 404 | Resource not found |
| 409 | Conflict (duplicate, constraint violation) |
| 500 | Internal server error |

### Headers

- X-Tenant-ID: Required tenant context (integer)
