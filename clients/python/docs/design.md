# mimir-client Design Document

**Status**: Proposed  
**Date**: 2026-02-20  
**Author**: Architecture Review  
**Package**: `mimir-client` (PyPI)

---

## Context

Multiple teams consuming the Mímir API have independently built Python HTTP wrappers. The agent team's client and the `mimir-semantic` library both contain ~600 lines of near-identical HTTP mapping code. This duplication violates DRY and creates version drift risk — when the API changes (e.g., v5.0.0 removing `DELETE /artifacts/{id}`), each wrapper must be independently updated.

## Decision

Provide an official thin Python client published to PyPI as `mimir-client`. The Mimir project owns and maintains it alongside the API, ensuring API and client versions stay synchronized.

---

## Scope

### What `mimir-client` IS

- A thin async HTTP wrapper mapping Python methods to Mímir REST endpoints
- Typed request/response models using Pydantic
- Automatic tenant header injection
- Structured error handling with typed exceptions
- Connection pooling via httpx
- Published to PyPI, installable via `pip install mimir-client`

### What `mimir-client` IS NOT

- A semantic layer (token budgeting, RAG policies, context assembly → `mimir-semantic`)
- An ORM or query builder
- A CLI tool
- A synchronous client (async-first; sync wrappers may be added later if demanded)

---

## Architecture

```
┌──────────────────────────────────────────────────┐
│           Application / Agent Code               │
└────────────────┬─────────────────────────────────┘
                 │ uses
                 ▼
┌──────────────────────────────────────────────────┐
│        mimir-semantic (optional)                 │
│  Context assembly, token budgeting, RAG policies │
└────────────────┬─────────────────────────────────┘
                 │ depends on
                 ▼
┌──────────────────────────────────────────────────┐
│           mimir-client (this package)            │
│  Typed Python methods → HTTP → Mímir API         │
│  pip install mimir-client                        │
└────────────────┬─────────────────────────────────┘
                 │ HTTP/REST
                 ▼
┌──────────────────────────────────────────────────┐
│           Mímir API (backend)                    │
│  FastAPI server, PostgreSQL + AGE                │
└──────────────────────────────────────────────────┘
```

### Dependency Direction

- `mimir-client` depends on: `httpx`, `pydantic`, `pydantic-settings`
- `mimir-semantic` depends on: `mimir-client` (replaces its embedded HTTP code)
- `backend` (the API server) NEVER imports from `mimir-client`

---

## API Coverage

The client provides methods for all Mímir API endpoints:

| Group | Endpoint | Client Method |
|-------|----------|---------------|
| **Health** | `GET /health` | `health()` |
| **Tenants** | `POST /tenants` | `create_tenant()` |
| | `GET /tenants` | `list_tenants()` |
| | `GET /tenants/{id}` | `get_tenant()` |
| | `DELETE /tenants/{id}` | `delete_tenant()` |
| **Artifact Types** | `GET /artifact-types` | `list_artifact_types()` |
| | `POST /artifact-types` | `create_artifact_type()` |
| **Artifacts** | `POST /artifacts` | `create_artifact()` |
| | `GET /artifacts` | `list_artifacts()` |
| | `GET /artifacts/{id}` | `get_artifact()` |
| | `GET /artifacts/{id}/children` | `get_artifact_children()` |
| **Relation Types** | `GET /relation-types` | `list_relation_types()` |
| | `POST /relation-types` | `create_relation_type()` |
| **Relations** | `POST /relations` | `create_relation()` |
| | `GET /relations` | `list_relations()` |
| | `GET /relations/{id}` | `get_relation()` |
| **Embedding Types** | `POST /embedding-types` | `create_embedding_type()` |
| | `GET /embedding-types` | `list_embedding_types()` |
| **Embeddings** | `POST /embeddings` | `create_embedding()` |
| | `POST /embeddings/generate` | `generate_embedding()` |
| **Search** | `POST /search` | `search()` |
| | `GET /search/fulltext` | `fulltext_search()` |
| **Context** | `POST /context` | `get_context()` |
| **Provenance** | `GET /provenance/artifact/{id}` | `get_artifact_provenance()` |

---

## Versioning Strategy

`mimir-client` version tracks the Mímir API major version:

| API Version | Client Version | Notes |
|-------------|---------------|-------|
| v5.0.0 | 5.0.0 | Initial release — matches current API |
| v5.0.1 | 5.0.x | Client bug fixes don't require API change |
| v6.0.0 | 6.0.0 | Breaking API change → new client major |

The version is defined in `clients/python/pyproject.toml` (single source of truth) and read via `importlib.metadata` at runtime.

**Constraint**: When bumping the backend API version, the client version MUST be bumped in the same release.

---

## Package Configuration

```toml
[project]
name = "mimir-client"
version = "5.0.0"
description = "Official Python client for the Mímir Knowledge Graph API"
requires-python = ">=3.11"

dependencies = [
    "httpx>=0.27",
    "pydantic>=2.0",
    "pydantic-settings>=2.0",
]
```

### Why `>=3.11` not `>=3.13`

The backend requires 3.13, but clients should support the broadest reasonable range. Python 3.11+ gives us `ExceptionGroup`, `TaskGroup`, and modern type syntax. Most consumer environments (agent frameworks, notebooks) may not be on 3.13 yet.

---

## Error Handling

All API errors are mapped to typed exceptions:

| HTTP Status | Exception | Use Case |
|-------------|-----------|----------|
| Connection failure | `MimirConnectionError` | Server unreachable |
| 404 | `MimirNotFoundError` | Resource doesn't exist |
| 422 | `MimirValidationError` | Invalid request data |
| 401/403 | `MimirAuthError` | Authentication failure (future) |
| 4xx/5xx | `MimirAPIError` | All other API errors |
| Missing tenant | `MimirTenantError` | No tenant_id configured |

All exceptions inherit from `MimirError` for catch-all handling.

---

## Configuration

```python
from mimir_client import MimirClient

# Explicit
client = MimirClient(
    base_url="http://localhost:38000",
    tenant_id=1,
)

# From environment variables
client = MimirClient.from_env()

# As async context manager
async with MimirClient.from_env() as client:
    artifact = await client.get_artifact("abc123-...")
```

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `MIMIR_API_URL` | Base URL for Mímir API | `http://localhost:38000` |
| `MIMIR_TENANT_ID` | Default tenant ID | (none) |
| `MIMIR_TIMEOUT` | Request timeout in seconds | `30.0` |

---

## PyPI Publishing

### GitHub Actions Integration

A `publish-client` job is added to the existing `release.yaml` workflow. On every `v*` tag push:

1. Docker image is built and pushed (existing)
2. `mimir-client` wheel is built and published to PyPI (new)
3. GitHub Release is created (existing)

### Requirements

- `PYPI_API_TOKEN` secret configured in GitHub repository settings
- Token scoped to `mimir-client` package on PyPI
- Package name `mimir-client` registered on PyPI (first publish claims it)

### Build Process

```yaml
- name: Build mimir-client
  run: |
    cd clients/python
    pip install build
    python -m build

- name: Publish to PyPI
  uses: pypa/gh-action-pypi-publish@release/v1
  with:
    packages-dir: clients/python/dist/
    password: ${{ secrets.PYPI_API_TOKEN }}
```

---

## Migration Plan

### For `mimir-semantic`

1. Add `mimir-client>=5.0.0` as a dependency
2. Remove `client.py`, `config.py`, `exceptions.py` from `mimir_semantic`
3. Import from `mimir_client` instead
4. `MimirClient` moves from `mimir_semantic.client` → `mimir_client.MimirClient`
5. Re-export from `mimir_semantic` for backward compatibility during transition

### For the Agent Team

1. Replace their internal client with `pip install mimir-client`
2. Update imports: `from mimir_client import MimirClient`
3. API is intentionally similar to what they already have

---

## What This Design Does NOT Specify

Per RULES.md — this design defines interfaces and constraints, not implementations:

- Exact method signatures (the implementing engineer decides based on the API schema)
- Internal HTTP retry/backoff strategy
- Response caching approach
- Logging implementation
- Test fixture strategy

The implementing engineer should study the existing `mimir-semantic/client.py` and the agent team's client, take the best patterns from each, and make their own implementation decisions within these constraints.

---

## Success Criteria

1. `pip install mimir-client` works from PyPI
2. All Mímir API endpoints have corresponding client methods
3. `mimir-semantic` can replace its embedded HTTP code with `mimir-client`
4. Automated publishing on every `v*` tag via GitHub Actions
5. Version reported by `mimir_client.__version__` matches `pyproject.toml`