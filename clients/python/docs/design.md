# Mimir Python Client Library -- Design Document

**Date:** 2026-03-19
**From:** Chief Systems Architect
**To:** Product Owner
**Status:** Draft -- awaiting approval

---

## Purpose

This document specifies what the official Mimir Python client library must do and how its interfaces interact. It does not prescribe implementation details -- the implementing engineer chooses HTTP libraries, error handling internals, and code organization within these constraints.

---

## Problem

External teams integrating with Mimir are building their own HTTP client wrappers. These wrappers make design decisions that diverge from Mimir's actual API semantics -- most notably around tenant scoping. An official client that accurately reflects the API's design would eliminate this class of integration error and reduce the effort required to adopt Mimir.

---

## Scope

The client covers the full Mimir REST API surface:

- Tenant management
- Artifact lifecycle (CRUD + listing)
- Artifact type management
- Relation lifecycle (CRUD + listing)
- Relation type management
- Embedding storage and retrieval
- Embedding type management
- Search (keyword, semantic, graph, unified)
- Context assembly
- Provenance recording and retrieval

The client is a thin, typed wrapper over HTTP. It does not embed business logic, caching, retry policies, or connection pooling beyond what the underlying HTTP library provides.

---

## Consumer Profiles

| Consumer | Needs | Frequency |
|----------|-------|-----------|
| Agent systems (LLM pipelines) | Store artifacts, search, retrieve context | High-volume, single-tenant typical |
| CLI tools and scripts | CRUD operations, bulk ingestion | Batch, possibly multi-tenant |
| Integration tests | Full API coverage, tenant lifecycle | Per-test-run, disposable tenants |
| Dashboards and reporting | Search, context assembly, read-heavy | Read-heavy, possibly cross-tenant |

---

## Interface Constraints

### 1. Sync-first interface

The client provides a synchronous interface. This is the correct default per our interface design rules:

- The majority of known callers (agent systems, CLI tools, scripts, tests) are synchronous or can trivially wrap sync calls.
- Sync callers wrapping async code hit event loop nesting problems.
- Async callers can wrap sync code trivially via `asyncio.to_thread()`.

If async demand materializes, an async variant can be added later with a sync wrapper. The sync interface is not deprecated by this -- both coexist.

### 2. Tenant is per-call with an optional default

The Mimir API accepts tenant as an `X-Tenant-ID` header (integer) on every data operation. The client must reflect this accurately:

- Every data method accepts an optional `tenant_id: int` parameter.
- If `tenant_id` is not provided on a call, the client uses a default tenant set at construction.
- If neither is set, the client raises an error immediately (fail fast).
- Tenant management operations (`create_tenant`, `get_tenant`, `list_tenants`, `delete_tenant`) are not tenant-scoped -- they operate at the system level.
- Tenant IDs are integers, not strings. The API uses integer primary keys for tenants.

This design accurately represents the API: a single client instance can operate across tenants, but the common single-tenant case requires no per-call boilerplate.

### 3. Construction

The client is constructed with:

| Parameter | Required | Purpose |
|-----------|----------|---------|
| `base_url` | Yes | Mimir API base URL (e.g., `http://localhost:8000`) |
| `default_tenant` | No | Default tenant ID (integer) used when per-call `tenant_id` is omitted |
| `timeout` | No | Request timeout in seconds (sensible default) |
| `headers` | No | Additional HTTP headers applied to all requests (e.g., auth tokens) |

The client does not read environment variables. Configuration is the caller's responsibility. This keeps the client pure and testable.

### 4. Error model

The client translates HTTP responses into a clear error hierarchy:

| HTTP Status | Client Behavior |
|-------------|----------------|
| 2xx | Return parsed response |
| 404 | Raise a specific not-found error with the entity type and identifier |
| 409 | Raise a specific conflict error (duplicate key, etc.) |
| 422 | Raise a validation error with the detail from the response body |
| 4xx (other) | Raise a client error with status code and response body |
| 5xx | Raise a server error with status code and response body |
| Connection failure | Raise a connection error |

All errors carry the HTTP status code, response body, and the request URL for diagnostics. The error hierarchy allows callers to catch broadly (`MimirError`) or narrowly (`NotFoundError`, `ValidationError`).

### 5. Return types

All methods return typed data objects (dataclasses or similar). The client does not return raw dicts or HTTP responses. This provides IDE autocompletion, type safety, and a stable interface that does not change if the HTTP response format adds optional fields.

The data objects mirror the API's response schemas but are client-side types -- they are not imports from the server codebase. The client and server share no code.

---

## Component Interfaces

### Tenant Operations

These are system-level operations, not scoped to a tenant. Tenant IDs are server-assigned integers.

| Operation | Input | Output | Notes |
|-----------|-------|--------|-------|
| `create_tenant` | `shortname: str`, `name: str`, `tenant_type: str (optional)`, `description: str (optional)` | `Tenant` | Returns server-assigned integer ID |
| `get_tenant` | `tenant_id: int` | `Tenant` | 404 if not found |
| `get_tenant_by_shortname` | `shortname: str` | `Tenant` | 404 if not found |
| `list_tenants` | `active_only: bool (optional)` | `list[Tenant]` | All tenants |
| `update_tenant` | `tenant_id: int`, `name: str (optional)`, `description: str (optional)`, `is_active: bool (optional)` | `Tenant` | Partial update |
| `delete_tenant` | `tenant_id: int` | `None` | Cascading delete of all data, 404 if not found |

### Artifact Type Operations

Artifact types define the kinds of artifacts a tenant stores. These are system-level vocabulary tables, not tenant-scoped.

| Operation | Input | Output | Notes |
|-----------|-------|--------|-------|
| `create_artifact_type` | `code: str`, `display_name: str`, `description: str (optional)`, `category: str (optional)` | `ArtifactType` | |
| `get_artifact_type` | `code: str` | `ArtifactType` | By code |
| `list_artifact_types` | `active_only: bool (optional)`, `category: str (optional)` | `list[ArtifactType]` | |
| `update_artifact_type` | `code: str`, `display_name: str (optional)`, `description: str (optional)`, `is_active: bool (optional)` | `ArtifactType` | Partial update |

### Artifact Operations

Artifacts are append-only. There are no update or delete operations on artifacts. Cleanup happens via tenant-level deletion (FK CASCADE).

| Operation | Input | Output | Notes |
|-----------|-------|--------|-------|
| `create_artifact` | `artifact_type: str`, `title: str (optional)`, `content: str (optional)`, `id: UUID (optional)`, `parent_artifact_id: UUID (optional)`, `metadata: dict (optional)`, `tenant_id: int (optional)` | `Artifact` | Client-generated UUID accepted; 409 if duplicate |
| `get_artifact` | `artifact_id: UUID`, `tenant_id: int (optional)` | `Artifact` | 404 if not found |
| `list_artifacts` | `artifact_type: str (optional)`, `limit: int (optional)`, `offset: int (optional)`, `ids: list[UUID] (optional)`, `tenant_id: int (optional)` | `ArtifactList` | Paginated; batch retrieval via `ids` |
| `get_children` | `artifact_id: UUID`, `tenant_id: int (optional)` | `list[Artifact]` | Positional child artifacts |

### Relation Type Operations

Relation types define the kinds of relationships between artifacts. System-level vocabulary, not tenant-scoped.

| Operation | Input | Output | Notes |
|-----------|-------|--------|-------|
| `create_relation_type` | `code: str`, `display_name: str`, `description: str (optional)`, `inverse_code: str (optional)`, `is_symmetric: bool (optional)` | `RelationType` | |
| `get_relation_type` | `code: str` | `RelationType` | |
| `get_inverse_relation_type` | `code: str` | `RelationType` | Returns the inverse type |
| `list_relation_types` | `active_only: bool (optional)` | `list[RelationType]` | |
| `update_relation_type` | `code: str`, ... | `RelationType` | Partial update |

### Relation Operations

Relations are append-only. Both source and target must be in the same tenant. There is no delete operation on relations.

| Operation | Input | Output | Notes |
|-----------|-------|--------|-------|
| `create_relation` | `source_id: UUID`, `target_id: UUID`, `relation_type: str`, `id: UUID (optional)`, `confidence: float (optional)`, `metadata: dict (optional)`, `tenant_id: int (optional)` | `Relation` | 409 if duplicate (same source, target, type) |
| `get_relation` | `relation_id: UUID`, `tenant_id: int (optional)` | `Relation` | |
| `list_relations` | `source_id: UUID (optional)`, `target_id: UUID (optional)`, `relation_type: str (optional)`, `tenant_id: int (optional)` | `RelationList` | Filter by source, target, or type |
| `get_artifact_relations` | `artifact_id: UUID`, `as_source: bool (optional)`, `as_target: bool (optional)`, `relation_type: str (optional)`, `tenant_id: int (optional)` | `list[Relation]` | All relations for an artifact |

### Embedding Type Operations

Embedding types define the vector models used for semantic search. System-level vocabulary. Creating a type auto-creates the backing vector table with HNSW index.

| Operation | Input | Output | Notes |
|-----------|-------|--------|-------|
| `create_embedding_type` | `code: str`, `display_name: str`, `provider: str`, `dimensions: int`, `distance_metric: str (optional)`, `description: str (optional)` | `EmbeddingType` | Creates vector table; 409 if exists |
| `get_embedding_type` | `code: str` | `EmbeddingType` | |
| `list_embedding_types` | `active_only: bool (optional)`, `provider: str (optional)` | `list[EmbeddingType]` | |
| `deactivate_embedding_type` | `code: str` | `None` | Soft delete; vector table retained |

### Embedding Operations

Embeddings are append-only. The `embedding_type` must be registered before creating embeddings. Vector dimensions must match the type definition.

| Operation | Input | Output | Notes |
|-----------|-------|--------|-------|
| `create_embedding` | `artifact_id: UUID`, `embedding_type: str`, `embedding: list[float]`, `metadata: dict (optional)`, `tenant_id: int (optional)` | `Embedding` | 400 if dimensions mismatch |
| `get_embedding` | `embedding_id: UUID`, `include_vector: bool (optional)`, `tenant_id: int (optional)` | `Embedding` | Vector omitted by default for performance |
| `list_embeddings` | `artifact_id: UUID (optional)`, `embedding_type: str (optional)`, `tenant_id: int (optional)` | `EmbeddingList` | Filter by artifact or type |
| `find_similar` | `query_vector: list[float]`, `embedding_type: str`, `limit: int (optional)`, `similarity_threshold: float (optional)`, `artifact_types: list[str] (optional)`, `tenant_id: int (optional)` | `SimilaritySearchResponse` | Low-level vector similarity |

### Search Operations

Search combines keyword, semantic, and graph-based retrieval.

| Operation | Input | Output | Notes |
|-----------|-------|--------|-------|
| `search` | `query: str`, `artifact_type: str (optional)`, `limit: int (optional)`, `tenant_id: str (optional)` | `list[SearchResult]` | Keyword search |
| `search_semantic` | `query: str`, `embedding_type: str (optional)`, `artifact_type: str (optional)`, `limit: int (optional)`, `tenant_id: str (optional)` | `list[SearchResult]` | Vector similarity search |
| `search_unified` | See below | `UnifiedSearchResult` | Combined multi-mode search |

**Unified search** is the primary search interface. It accepts:

| Parameter | Type | Required | Notes |
|-----------|------|----------|-------|
| `query` | `str` | Yes | Search text |
| `search_modes` | `list[str]` | No | Subset of `["keyword", "semantic", "graph"]`. Default: all available |
| `artifact_type` | `str` | No | Filter results to this artifact type |
| `embedding_type` | `str` | No | Which embedding type to use for semantic mode |
| `limit` | `int` | No | Max results per mode |
| `graph_seed_id` | `str` | No | Artifact ID to use as graph scope seed |
| `graph_max_depth` | `int` | No | Hops from seed for graph scoping |
| `tenant_id` | `str` | No | Tenant override |

The response includes per-mode results and a merged, deduplicated result list with scores.

### Context Operations

Context assembly retrieves an artifact and its neighborhood for LLM consumption.

| Operation | Input | Output | Notes |
|-----------|-------|--------|-------|
| `get_context` | `artifact_ids: list[str]`, `max_depth: int (optional)`, `max_tokens: int (optional)`, `strategy: str (optional)`, `tenant_id: str (optional)` | `ContextResult` | Strategy: `balanced`, `depth_first`, `breadth_first` |

The `ContextResult` includes:

- The requested artifacts with full content
- Related artifacts discovered by graph traversal (up to `max_depth` hops)
- The relations connecting them
- Token count and truncation metadata

### Provenance Operations

Provenance events are auto-created by the server when artifacts, relations, and embeddings are created. The client provides read-only access. There is no manual provenance creation endpoint.

| Operation | Input | Output | Notes |
|-----------|-------|--------|-------|
| `list_provenance` | `entity_type: str (optional)`, `entity_id: UUID (optional)`, `action: str (optional)`, `actor_type: str (optional)`, `tenant_id: int (optional)` | `ProvenanceList` | Filterable |
| `get_artifact_provenance` | `artifact_id: UUID`, `tenant_id: int (optional)` | `list[ProvenanceEvent]` | Full history for one artifact |

---

## Data Objects

The client returns typed objects, not dicts. Each object maps to an API response schema.

### Core entities

| Object | Key fields |
|--------|------------|
| `Tenant` | `id: int`, `shortname`, `name`, `tenant_type`, `description`, `is_active`, `metadata`, `created_at` |
| `Artifact` | `id: UUID`, `tenant_id`, `artifact_type`, `title`, `content`, `parent_artifact_id`, `metadata`, `content_hash`, `created_at` |
| `ArtifactType` | `code`, `display_name`, `description`, `category`, `is_active`, `created_at` |
| `Relation` | `id: UUID`, `tenant_id`, `source_id`, `target_id`, `relation_type`, `confidence`, `metadata`, `created_at` |
| `RelationType` | `code`, `display_name`, `description`, `inverse_code`, `is_symmetric`, `is_active`, `created_at` |
| `Embedding` | `id: UUID`, `tenant_id`, `artifact_id`, `embedding_type`, `metadata`, `created_at` |
| `EmbeddingType` | `code`, `display_name`, `provider`, `dimensions`, `distance_metric`, `vector_table_name`, `is_active`, `created_at` |
| `ProvenanceEvent` | `id: UUID`, `tenant_id`, `entity_type`, `entity_id`, `action`, `actor_type`, `actor_id`, `reason`, `metadata`, `created_at` |

### Search and context

| Object | Key fields |
|--------|------------|
| `SearchResult` | `artifact`, `score`, `rank` |
| `SearchResponse` | `results`, `total`, `query`, `strategy` |
| `GraphScope` | `root_artifact_id`, `max_depth`, `relation_types`, `direction` |
| `ContextResponse` | `artifact`, `context: list[ContextArtifact]`, `policy`, `hints_applied`, `metadata` |
| `ContextArtifact` | `artifact`, `relation_path`, `distance`, `relevance_score`, `inclusion_reason` |

---

## Non-functional Constraints

### What the client does NOT do

| Concern | Rationale |
|---------|-----------|
| Read environment variables | Configuration is the caller's responsibility. Keeps the client pure and testable. |
| Implement retry logic | Callers have different retry requirements. The client raises errors; callers decide retry policy. |
| Cache responses | Callers know their freshness requirements. The client is stateless per-request. |
| Manage connection pools | Delegated to the underlying HTTP library. The client does not add pooling abstractions. |
| Embed vector generation | The client stores pre-computed vectors. Embedding generation is a separate concern (see `mimir-embeddings` package). |
| Share code with the server | The client is independently typed. Server schema changes are absorbed by updating the client, not by importing server code. |

### Documentation Requirements

Every public method must have a docstring that is succinct but complete. The docstring is the primary interface documentation for users -- many will never read this design document or the API docs.

**Mandatory docstring content for every public method:**

1. **One-line summary.** What the method does, in a single sentence.
2. **Tenant behavior.** Every tenant-scoped method must state: "Uses `tenant_id` if provided, otherwise falls back to `default_tenant`. Raises `MimirError` if neither is set." This must not be buried or implied -- it must be explicit in every method that accepts `tenant_id`, because this is the single most common source of integration confusion.
3. **Key constraints.** Append-only operations (artifacts, relations, embeddings) must note that updates and deletes are not supported. Methods that require prerequisite resources (e.g., `create_embedding` requires a registered `embedding_type`) must state the prerequisite.
4. **Error cases.** Which specific exceptions the method raises and under what conditions (404, 409, 422).
5. **Args and Returns.** Typed parameter descriptions and return type.

**Source material:** The Mimir HTTP API is fully documented in OpenAPI 3.0 (available at `/openapi.json` and rendered at `/docs` and `/redoc`). The client's docstrings should pass through the semantics from the OpenAPI descriptions -- parameter constraints, valid values, error conditions, and behavioral notes. The implementing engineer should use the OpenAPI spec as the authoritative source for endpoint behavior and translate it into the client's docstrings.

**Multi-tenant clarity.** The following points must be documented clearly, not just in a README but in the relevant method docstrings:

- A single client instance can operate across multiple tenants by passing `tenant_id` per call.
- The `default_tenant` is a convenience default, not a lock. It can be overridden on any call.
- Relations, graph traversal, and context queries are tenant-internal. You cannot create a relation between artifacts in different tenants, and a context expansion in tenant A will not surface artifacts from tenant B.
- Tenant management operations (`create_tenant`, `list_tenants`, `get_tenant`, `delete_tenant`) are system-level and do not use `tenant_id` / `default_tenant`.
- `delete_tenant` cascades to all artifacts, relations, embeddings, and provenance within that tenant.

**Tone:** Engineering clarity. No filler, no marketing language, no "simply" or "just". State what the method does, what it requires, and what can go wrong.

### What the client MUST do

| Concern | Requirement |
|---------|-------------|
| Fail fast on missing tenant | If no `tenant_id` is provided and no default is set, raise immediately. Do not send a malformed request. |
| Validate vector dimensions locally | Before sending an embedding, check that the vector length is positive and non-zero. Do not send empty vectors. |
| Provide diagnostic context in errors | Every error includes the HTTP method, URL, status code, and response body. Callers should never need to enable debug logging to understand a failure. |
| Support `with` statement | The client is a context manager for clean resource cleanup (HTTP connections). |
| Be thread-safe | Multiple threads can share one client instance. The underlying HTTP library must support this. |

### Packaging

| Aspect | Decision |
|--------|----------|
| Package name | `mimir-client` |
| Import path | `from mimir_client import MimirClient` |
| Build backend | `hatchling` (PEP 621) |
| Source layout | `src/mimir_client/` |
| Python version | `>=3.13` |
| Dependencies | HTTP library, `pydantic` or dataclasses for models. Minimal dependency footprint. |

---

## Interaction Patterns

### Single-tenant agent (most common)

```
client = MimirClient(base_url="http://mimir:8000", default_tenant=1)
artifact = client.create_artifact(title="Requirements v1", body="...", artifact_type="requirement")
results = client.search_unified(query="authentication requirements")
context = client.get_context(artifact_ids=[artifact.id], max_depth=2)
```

### Multi-tenant script

```
client = MimirClient(base_url="http://mimir:8000")
team_a_artifacts = client.list_artifacts(tenant_id=1)
team_b_artifacts = client.list_artifacts(tenant_id=2)
```

### Integration test with disposable tenant

```
with MimirClient(base_url="http://mimir:8000") as client:
    tenant = client.create_tenant(shortname="test-run-abc", name="Test Run", tenant_type="experiment")
    # tenant.id is the server-assigned integer
    test_client = MimirClient(base_url="http://mimir:8000", default_tenant=tenant.id)
    # ... test operations ...
    client.delete_tenant(tenant_id=tenant.id)
```

### Error handling

```
from mimir_client import MimirClient, NotFoundError, ValidationError

client = MimirClient(base_url="http://mimir:8000", default_tenant=1)
try:
    artifact = client.get_artifact("nonexistent-id")
except NotFoundError as e:
    print(f"Artifact not found: {e.entity_id}")
    print(f"HTTP {e.status_code}: {e.response_body}")
except ValidationError as e:
    print(f"Invalid request: {e.detail}")
```

---

## Boundaries and Trade-offs

### Why sync-only at launch

An async interface doubles the API surface and test surface. The sync interface serves all known consumers today. The wrapping asymmetry (async callers wrap sync trivially; sync callers wrapping async is error-prone) means sync is the lower-risk default. An async variant can be added later without breaking the sync interface.

### Why no environment variable reading

Every client library that reads environment variables eventually collides with the caller's configuration system. Agent frameworks, CLI tools, and test harnesses all have their own config loading. The client should be a tool the caller configures, not a tool that configures itself.

### Why no shared code with the server

Sharing Pydantic models between server and client creates a deployment coupling: upgrading the server requires upgrading the client, even for additive non-breaking changes. Independent types allow the client to evolve at its own pace and tolerate fields being added to API responses without breaking.

### Why per-call tenant with default

This accurately reflects the API. The API accepts tenant per-request via `X-Tenant-ID` header. A client that locks tenant at construction misrepresents the API's capabilities and creates the exact misconfiguration we observed in the external team's integration. The default is a convenience, not a constraint.

### Append-only data model

Artifacts, relations, and embeddings are append-only in Mimir. There are no update or delete endpoints for these entities. This is a deliberate design decision: versioning is handled via `supersedes` relations (editorial intent), and cleanup happens via tenant-level deletion which cascades to all associated data. The client must not expose update or delete methods for these entities.

---

## Open Questions for Product Owner

1. **Package distribution.** Should this be published to PyPI as `mimir-client`, or distributed only as a Git dependency? PyPI is the standard Python distribution channel and enables `pip install mimir-client`. Git dependency works but adds friction.

2. **Versioning strategy.** Should the client version track the API version, or version independently? Independent versioning is more flexible but requires a compatibility matrix. Tracking the API version is simpler but forces client releases for non-breaking API changes.

3. **Embedding generation convenience.** The client stores pre-computed vectors. Should we provide an optional integration with `mimir-embeddings` that combines generation and storage? This would be a separate convenience function, not a core client feature, but it would simplify the most common embedding workflow.

---

## Addenda

### CLI-01: Tenant Shortname as Primary Identifier (2026-03-29)

Section 2 ("Tenant is per-call with an optional default") states: "Tenant IDs
are integers, not strings. The API uses integer primary keys for tenants." This
accurately describes the backend wire protocol (`X-Tenant-ID` header) but was
incorrectly promoted to the client's public interface.

**Correction:** The client's public constructor and configuration now accept
`tenant: str` (domain shortname) as the primary tenant identifier. The integer
surrogate key is resolved lazily and cached internally. The `tenant_id: int`
parameter is deprecated (v5.3.0) and will be removed in v6.0.0.

Section 2 also describes per-call `tenant_id` on every data method. This was
never implemented in v5.2.0 -- the client uses a single `X-Tenant-ID` header
set at the httpx.Client level with no per-method override. CLI-01 does not
introduce this feature. If per-call tenant override is needed in the future, it
will be evaluated as part of the v6.0.0 multi-tenant agent experience work (see
`docs/roadmap.md`).

All other constraints in this design document remain in force: thin wrapper, no
caching beyond tenant resolution, no retry logic, fail fast on missing tenant,
context manager support, thread safety.

See `cli-01-design.md` for the full design document.
