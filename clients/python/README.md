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
    async with MimirClient(base_url="http://localhost:38000", tenant_id=1) as client:
        # Check API health
        health = await client.health()
        print(health["version"])

        # Create an artifact
        artifact = await client.create_artifact(
            artifact_type="document",
            title="Meeting Notes",
            content="Discussion about Q1 goals...",
        )
        print(artifact["id"])

        # Search
        results = await client.search(query="Q1 goals")
        for r in results["results"]:
            print(r["title"], r["score"])

asyncio.run(main())
```

## Configuration

### From environment variables

```python
client = MimirClient.from_env()
```

| Variable | Description | Default |
|----------|-------------|---------|
| `MIMIR_API_URL` | Base URL for Mímir API | `http://localhost:38000` |
| `MIMIR_TENANT_ID` | Default tenant ID | (none) |
| `MIMIR_TIMEOUT` | Request timeout in seconds | `30.0` |

### Explicit

```python
client = MimirClient(
    base_url="https://mimir.example.com",
    tenant_id=42,
    timeout=60.0,
)
```

## Error Handling

```python
from mimir_client.exceptions import MimirNotFoundError, MimirValidationError

try:
    artifact = await client.get_artifact("nonexistent-id")
except MimirNotFoundError:
    print("Artifact not found")
except MimirValidationError as e:
    print(f"Validation errors: {e.errors}")
```

## API Coverage

All Mímir API endpoints have corresponding client methods. See [docs/design.md](docs/design.md) for the full coverage matrix.

## Development

```bash
cd clients/python
uv venv .venv
source .venv/bin/activate
uv pip install -e ".[dev]"
pytest -v
```

## License

MIT