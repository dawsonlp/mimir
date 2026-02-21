# mimir-client

Official Python client for the [Mímir Knowledge Graph API](https://github.com/dawsonlp/mimir).

## Installation

```bash
pip install mimir-client
```

## Quick Start

```python
import asyncio
from mimir_client import MimirClient

async def main():
    async with MimirClient(api_url="http://localhost:38000", tenant_id=1) as client:
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
        print(f"Created: {artifact.id} — {artifact.title}")

        # Search
        results = await client.search(query="architecture")
        for r in results.results:
            print(f"  [{r.score:.2f}] {r.artifact.title}")

asyncio.run(main())
```

## Configuration

### Direct instantiation

```python
client = MimirClient(
    api_url="http://localhost:38000",
    tenant_id=1,
    timeout=30.0,
)
```

### From environment variables

```python
from mimir_client import MimirClient, get_settings

# Reads MIMIR_API_URL, MIMIR_TENANT_ID, MIMIR_TIMEOUT from env / .env
settings = get_settings()
client = MimirClient.from_settings(settings)
```

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `MIMIR_API_URL` | `http://localhost:38000` | Mímir API base URL |
| `MIMIR_TENANT_ID` | `None` | Default tenant ID |
| `MIMIR_TIMEOUT` | `30.0` | Request timeout (seconds) |

## API Coverage

All Mímir v5 REST endpoints are covered:

| Resource | Methods |
|----------|---------|
| **Tenants** | `create_tenant`, `get_tenant`, `get_tenant_by_shortname`, `list_tenants`, `update_tenant`, `delete_tenant`, `ensure_tenant` |
| **Artifact Types** | `create_artifact_type`, `get_artifact_type`, `list_artifact_types`, `update_artifact_type`, `ensure_artifact_type` |
| **Artifacts** | `create_artifact`, `get_artifact`, `list_artifacts`, `get_children` |
| **Relation Types** | `create_relation_type`, `get_relation_type`, `list_relation_types`, `update_relation_type`, `get_inverse_relation_type`, `ensure_relation_type` |
| **Relations** | `create_relation`, `get_relation`, `list_relations`, `get_artifact_relations` |
| **Embedding Types** | `create_embedding_type`, `get_embedding_type`, `list_embedding_types`, `delete_embedding_type`, `ensure_embedding_type` |
| **Embeddings** | `create_embedding`, `get_embedding`, `list_embeddings` |
| **Search** | `search` (unified), `search_fulltext` |
| **Context** | `get_context` |
| **Provenance** | `list_provenance_by_artifact`, `list_provenance_by_source` |
| **Health** | `health`, `is_healthy` |

## Typed Responses

All methods return Pydantic models with full type information:

```python
artifact = await client.create_artifact("document", title="Test")
print(artifact.id)          # UUID
print(artifact.title)       # str | None
print(artifact.created_at)  # datetime
```

## Error Handling

Errors are mapped to typed exceptions:

```python
from mimir_client import MimirNotFoundError, MimirConflictError

try:
    artifact = await client.get_artifact("nonexistent-uuid")
except MimirNotFoundError:
    print("Artifact not found")

try:
    await client.create_relation(src_id, tgt_id, "derived_from")
except MimirConflictError:
    print("Relation already exists")
```

| HTTP Status | Exception |
|------------|-----------|
| Connection failure | `MimirConnectionError` |
| 404 | `MimirNotFoundError` |
| 409 | `MimirConflictError` |
| 422 | `MimirValidationError` |
| 5xx | `MimirServerError` |
| Other 4xx | `MimirError` |

## Convenience Methods

`ensure_*` methods are idempotent — they return existing resources or create new ones:

```python
# Safe to call repeatedly — no-op if already exists
tenant = await client.ensure_tenant("dev", "Development")
await client.ensure_artifact_type("document", "Document", category="content")
await client.ensure_relation_type("derived_from", "Derived From", inverse_code="source_of")
await client.ensure_embedding_type("nomic", provider="ollama", dimensions=768)
```

## Scope

This client is a **thin HTTP wrapper**. It does NOT include:

- Embedding generation (use [`mimir-semantic`](../../semantic/) for Ollama/OpenAI/Voyage integration)
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
