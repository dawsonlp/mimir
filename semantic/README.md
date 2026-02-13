# Mímir Semantic Layer

Python client library for intelligent context assembly and semantic operations built on the Mímir Storage API.

## Overview

The Semantic Layer provides high-level operations for:

- **Context Assembly**: Gather related artifacts using lineage, similarity, and custom policies
- **Semantic Search**: Find relevant content using vector similarity and hybrid search
- **Token Budgeting**: Manage context size for LLM prompts
- **Provenance Tracing**: Navigate artifact lineage and derivation chains

This library communicates with Mímir exclusively via its REST API, maintaining a clean separation between storage primitives and semantic interpretation.

## Installation

```bash
cd semantic
poetry install
```

## Quick Start

```python
import asyncio
from mimir_semantic import MimirClient

async def main():
    # Create client (reads from environment or use explicit config)
    client = MimirClient(
        base_url="http://localhost:38000",
        tenant_id=1,
    )
    
    # Or from environment variables
    client = MimirClient.from_env()
    
    # Get an artifact
    artifact = await client.get_artifact("abc123-...")
    
    # Gather context for RAG
    context = await client.gather_context(
        artifact_id="abc123-...",
        depth=2,
        token_budget=4000,
    )
    
    await client.close()

asyncio.run(main())
```

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `MIMIR_API_URL` | Base URL for Mímir Storage API | `http://localhost:38000` |
| `MIMIR_DOCS_URL` | Base URL for API documentation | `{MIMIR_API_URL}/docs` |
| `MIMIR_TENANT_ID` | Default tenant ID | (none) |

### Client Initialization

```python
# Explicit configuration
client = MimirClient(
    base_url="https://api.mimir.example.com",
    docs_url="https://docs.mimir.example.com",
    tenant_id=42,
)

# From environment
client = MimirClient.from_env()
```

## Architecture

```
┌─────────────────────────────────────────────────┐
│           Application Layer                      │
│   Your code, RAG pipelines, chat applications   │
└────────────────┬────────────────────────────────┘
                 │ uses
                 ▼
┌─────────────────────────────────────────────────┐
│         Semantic Layer (this library)           │
│   Context assembly, search, token budgeting     │
│   mimir_semantic.MimirClient                    │
└────────────────┬────────────────────────────────┘
                 │ HTTP/REST
                 ▼
┌─────────────────────────────────────────────────┐
│           Storage Layer (Mímir API)             │
│   Artifacts, Relations, Embeddings, Provenance  │
│   http://localhost:38000                        │
└─────────────────────────────────────────────────┘
```

## Key Design Principles

1. **API-Only Access**: All storage operations go through the REST API. No direct database access.

2. **Documentation Transparency**: Every method documents the underlying API endpoint with links.

3. **Configurable URLs**: API and documentation URLs are configurable for different deployments.

4. **Storage Layer Ignorance**: The semantic layer never bypasses the storage API. If an operation can't be done through the API, we request an API enhancement.

## Documentation

Each client method includes comprehensive documentation:

```python
>>> help(client.create_artifact)

create_artifact(artifact_type, title, content=None, metadata=None)

    Create a new artifact in the storage layer.
    
    API Reference
    -------------
    POST /artifacts
    See: http://localhost:38000/docs#/Artifacts/create_artifact_artifacts_post
    
    ...
```

## Project Structure

```
semantic/
├── pyproject.toml          # Package configuration
├── README.md               # This file
├── docs/
│   ├── design.md           # Architecture and design decisions
│   └── api-requests.md     # Requested Storage API changes
├── src/
│   └── mimir_semantic/
│       ├── __init__.py     # Package exports
│       ├── client.py       # MimirClient - main entry point
│       ├── config.py       # Configuration management
│       ├── models.py       # Pydantic models
│       ├── context/        # Context assembly
│       ├── search/         # Semantic search helpers
│       └── exceptions.py   # Custom exceptions
└── tests/
    ├── conftest.py         # Test fixtures
    ├── test_client.py      # Client tests
    └── test_context.py     # Context assembly tests
```

## Development

```bash
# Install with dev dependencies
cd semantic
poetry install --with dev

# Run tests (requires running Mímir API)
poetry run pytest

# Format code
poetry run black src tests
poetry run ruff check --fix src tests

# Type checking
poetry run mypy src
```

## License

MIT