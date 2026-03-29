# mimir-client

Official Python client for the [Mimir Knowledge Graph API](https://github.com/dawsonlp/mimir).

## Installation

```bash
pip install mimir-client
```

## Quick Start

### Synchronous (recommended for scripts, CLI tools, and sync frameworks)

```python
from mimir_client import MimirSyncClient

with MimirSyncClient(api_url="http://localhost:38000", tenant="rademo1") as client:
    # Health check
    healthy = client.is_healthy()
    print(f"API healthy: {healthy}")

    # Create an artifact
    artifact = client.create_artifact(
        "document",
        title="Architecture Overview",
        content="This document describes the system architecture.",
        metadata={"author": "team-lead"},
    )
    print(f"Created: {artifact.id} -- {artifact.title}")

    # Search
    results = client.search(query="architecture")
    for r in results.results:
        print(f"  [{r.score:.2f}] {r.artifact.title}")
```

### Async (for asyncio applications)

```python
import asyncio
from mimir_client import MimirClient

async def main():
    async with MimirClient(api_url="http://localhost:38000", tenant="rademo1") as client:
        # Health check
        healthy = await client.is_healthy()
        print(f"API healthy: {healthy}")

        # Create an artifact
        artifact = await client.create_artifact(
            "document",
            title="Architecture Overview",
            content="This document describes the system architecture.",
            metadata={"author": "team-lead"},
        )
        print(f"Created: {artifact.id} -- {artifact.title}")

        # Search
        results = await client.search(query="architecture")
        for r in results.results:
            print(f"  [{r.score:.2f}] {r.artifact.title}")

asyncio.run(main())
```

Both clients have identical API surfaces. `MimirSyncClient` uses `httpx.Client` (blocking); `MimirClient` uses `httpx.AsyncClient`.

## Configuration

### Direct instantiation

```python
# Tenant identified by shortname (domain identifier)
client = MimirSyncClient(
    api_url="http://localhost:38000",
    tenant="rademo1",
    timeout=30.0,
)
```

The `tenant` parameter accepts the tenant shortname string. The client
resolves the shortname to the backend integer ID lazily on the first
tenant-scoped request. No manual ID lookup is needed.

### From environment variables

```python
from mimir_client import MimirSyncClient, MimirClient, get_settings

# Reads MIMIR_API_URL, MIMIR_TENANT, MIMIR_TIMEOUT from env / .env
settings = get_settings()

client = MimirSyncClient.from_settings(settings)  # sync
client = MimirClient.from_settings(settings)       # async
```

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `MIMIR_API_URL` | `http://localhost:38000` | Mimir API base URL |
| `MIMIR_TENANT` | `None` | Tenant shortname (e.g., `rademo1`) |
| `MIMIR_TIMEOUT` | `30.0` | Request timeout (seconds) |
| `MIMIR_TENANT_ID` | `None` | **Deprecated.** Integer tenant ID. Use `MIMIR_TENANT` instead. Will be removed in v6.0.0. |

### Multi-tenant agents

For agents operating across multiple knowledge graphs, use one client per tenant:

```python
org = MimirSyncClient(api_url="http://mimir:38000", tenant="rademo1-org")
practices = MimirSyncClient(api_url="http://mimir:38000", tenant="rademo1-practices")
project = MimirSyncClient(api_url="http://mimir:38000", tenant="rademo1-project-alpha")

# Each client resolves its own tenant independently
org_results = org.search(query="authentication patterns")
best_practices = practices.search(query="authentication best practices")
project_goals = project.search(query="security requirements")
```

### Backward compatibility

The `tenant_id: int` parameter is deprecated and will be removed in v6.0.0:

```python
# Deprecated -- emits DeprecationWarning
client = MimirSyncClient(api_url="http://localhost:38000", tenant_id=1)
```

Providing both `tenant` and `tenant_id` raises `ValueError`.

## API Coverage

All Mimir v5 REST endpoints are covered:

| Resource | Methods |
|----------|---------|
| **Tenants** | `create_tenant`, `get_tenant`, `get_tenant_by_shortname`, `list_tenants`, `update_tenant`, `delete_tenant`, `ensure_tenant` |
| **Artifact Types** | `create_artifact_type`, `get_artifact_type`, `list_artifact_types`, `update_artifact_type`, `ensure_artifact_type` |
| **Artifacts** | `create_artifact`, `get_artifact`, `list_artifacts`, `get_children` |
| **Relation Types** | `create_relation_type`, `get_relation_type`, `list_relation_types`, `update_relation_type`, `get_inverse_relation_type`, `ensure_relation_type` |
| **Relations** | `create_relation`, `get_relation`, `list_relations`, `get_artifact_relations` |
| **Embedding Types** | `create_embedding_type`, `get_embedding_type`, `list_embedding_types`, `delete_embedding_type`, `ensure_embedding_type` |
| **Embeddings** | `create_embedding`, `get_embedding`, `list_embeddings` |
| **Search** | `search` (unified), `search_fulltext`, `search_semantic`, `search_hybrid`, `search_similar` |
| **Context** | `get_context` |
| **Provenance** | `list_provenance`, `list_provenance_by_artifact` |
| **Health** | `health`, `is_healthy` |

## Typed Responses

All methods return Pydantic models with full type information:

```python
artifact = client.create_artifact("document", title="Test")
print(artifact.id)          # UUID
print(artifact.title)       # str | None
print(artifact.created_at)  # datetime
```

## Error Handling

Errors are mapped to typed exceptions:

```python
from mimir_client import MimirNotFoundError, MimirConflictError, MimirTenantError

try:
    artifact = client.get_artifact("nonexistent-uuid")
except MimirNotFoundError:
    print("Artifact not found")

try:
    client.create_relation(src_id, tgt_id, "derived_from")
except MimirConflictError:
    print("Relation already exists")
```

| HTTP Status | Exception |
|------------|-----------|
| Connection failure | `MimirConnectionError` |
| Missing/invalid tenant | `MimirTenantError` |
| 404 | `MimirNotFoundError` |
| 409 | `MimirConflictError` |
| 422 | `MimirValidationError` |
| 5xx | `MimirServerError` |
| Other 4xx | `MimirError` |

## Convenience Methods

`ensure_*` methods are idempotent -- they return existing resources or create new ones:

```python
tenant = client.ensure_tenant("dev", "Development")
client.ensure_artifact_type("document", "Document", category="content")
client.ensure_relation_type("derived_from", "Derived From", inverse_code="source_of")
client.ensure_embedding_type("nomic", provider="ollama", dimensions=768)
```

## Scope

This client is a **thin HTTP wrapper**. It does NOT include:

- Embedding generation (use [`mimir-semantic`](../../semantic/) for Ollama/OpenAI integration)
- Token budgeting or RAG policies
- Graph traversal algorithms
- Batch operations

## Requirements

- Python >= 3.11
- httpx
- pydantic >= 2.0
- pydantic-settings >= 2.0

## License

MIT