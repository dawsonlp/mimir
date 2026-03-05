# mimir-embeddings

Embedding generation library for Mimir. Provides provider abstraction over Ollama and OpenAI for converting text into vectors.

This is mechanism, not policy. The library does not prescribe how to ingest, retrieve, chunk, or assemble context. Applications compose this library with `mimir-client` to implement their own workflows.

## Installation

```bash
cd semantic
uv venv .venv
source .venv/bin/activate
uv pip install -e ".[dev]"
```

## Usage

### Ollama (local)

```python
from mimir_embeddings import OllamaProvider, OllamaConfig

async with OllamaProvider(OllamaConfig()) as provider:
    result = await provider.generate("Hello, world!")
    print(f"Dimensions: {result.dimensions}")
    print(f"Vector: {result.embedding[:5]}...")
```

### OpenAI

```python
from mimir_embeddings import OpenAIProvider, OpenAIConfig

config = OpenAIConfig(api_key="sk-...")
async with OpenAIProvider(config) as provider:
    result = await provider.generate("Hello, world!")
    print(f"Dimensions: {result.dimensions}")
    print(f"Tokens used: {result.token_count}")
```

### Batch generation

```python
results = await provider.generate_batch(["text one", "text two", "text three"])
# len(results) == 3, each with correct dimensions
```

### With mimir-client (application code)

```python
from mimir_embeddings import OllamaProvider, OllamaConfig
from mimir_client import MimirClient

async def ingest_document(text: str, artifact_id, tenant_id: int):
    async with OllamaProvider(OllamaConfig()) as provider:
        result = await provider.generate(text)

    async with MimirClient(api_url="http://localhost:38000", tenant_id=tenant_id) as client:
        await client.create_embedding(
            artifact_id=artifact_id,
            embedding_type_code="nomic-embed-text",
            embedding=result.embedding,
        )
```

## Configuration

Configuration uses environment variables with provider-specific prefixes:

| Variable | Provider | Default |
|----------|----------|---------|
| `MIMIR_EMBEDDINGS_OLLAMA_BASE_URL` | Ollama | `http://localhost:11434` |
| `MIMIR_EMBEDDINGS_OLLAMA_MODEL` | Ollama | `nomic-embed-text` |
| `MIMIR_EMBEDDINGS_OLLAMA_DIMENSIONS` | Ollama | `768` |
| `MIMIR_EMBEDDINGS_OLLAMA_TIMEOUT` | Ollama | `30.0` |
| `MIMIR_EMBEDDINGS_OPENAI_API_KEY` | OpenAI | (required) |
| `MIMIR_EMBEDDINGS_OPENAI_BASE_URL` | OpenAI | `https://api.openai.com/v1` |
| `MIMIR_EMBEDDINGS_OPENAI_MODEL` | OpenAI | `text-embedding-3-small` |
| `MIMIR_EMBEDDINGS_OPENAI_DIMENSIONS` | OpenAI | `1536` |
| `MIMIR_EMBEDDINGS_OPENAI_TIMEOUT` | OpenAI | `30.0` |

All values can be overridden via constructor parameters.

## Testing

```bash
# Unit tests (no external dependencies)
pytest tests/unit -v

# Integration tests (requires Ollama with nomic-embed-text)
pytest tests/integration -v -m integration
```

## Documentation

- [Architect Design](docs/design.md) — scope, constraints, trade-offs
- [Technical Design](docs/technical-design.md) — implementation decisions, module structure, testing strategy