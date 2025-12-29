# Mímir V2 - Knowledge Graph & Semantic Memory API

Unified artifact model knowledge graph API with semantic search capabilities.

## Quick Start

### Prerequisites

- Docker and Docker Compose
- `.env` file with credentials (copy from `.env.example`)

### Development Mode (with Hot-Reload)

```bash
cd v2

# Create .env file (one-time setup)
cp .env.example .env
# Edit .env to set POSTGRES_PASSWORD and optional API keys

# Start all services with hot-reload
docker compose up -d

# Run database migrations
docker compose exec api python -m migrations.migrate up
```

**Access points:**
- Landing Page: http://localhost:38000/
- Swagger UI: http://localhost:38000/docs
- ReDoc: http://localhost:38000/redoc
- OpenAPI Spec: http://localhost:38000/openapi.json
- Health Check: http://localhost:38000/health
- PostgreSQL: localhost:35432

### How Hot-Reload Works

The development setup uses `docker-compose.override.yaml` (automatically combined with `docker-compose.yaml`):

```yaml
services:
  api:
    volumes:
      - ./src:/app/src:ro          # Mount local source → container
      - ./migrations:/app/migrations:ro
    command: ["uvicorn", "mimir.main:app", "--reload", "--reload-dir", "/app/src"]
```

**Result:** Edit files in `v2/src/` → Changes apply immediately without rebuild.

### Production Mode (No Hot-Reload)

```bash
# Build with code baked into image
docker compose -f docker-compose.yaml build api

# Run without override file
docker compose -f docker-compose.yaml up -d
```

## Port Mapping

Host ports are prefixed with `3` to avoid conflicts with V1 or other services:

| Service    | Container Port | Host Port |
|------------|----------------|-----------|
| PostgreSQL | 5432           | 35432     |
| API        | 8000           | 38000     |

## Configuration

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `POSTGRES_PASSWORD` | Yes | Database password |
| `OPENAI_API_KEY` | No | For OpenAI embeddings |
| `OLLAMA_BASE_URL` | No | Ollama server URL (default: `http://host.docker.internal:11434`) |
| `DEFAULT_EMBEDDING_MODEL` | No | Default model (default: `nomic-embed-text`) |
| `LOG_LEVEL` | No | Logging level (default: `INFO`, dev: `DEBUG`) |

### Embedding Providers

V2 supports multiple embedding providers:
- **Ollama** (local): `nomic-embed-text`, `mxbai-embed-large`
- **OpenAI**: `text-embedding-3-small`, `text-embedding-3-large`

## Project Structure

```
v2/
├── docker-compose.yaml           # Production services
├── docker-compose.override.yaml  # Development overrides (hot-reload)
├── .env.example                  # Environment template
├── pyproject.toml               # Python dependencies
├── src/mimir/                   # Application source
│   ├── main.py                  # FastAPI application
│   ├── config.py                # Settings management
│   ├── database.py              # psycopg connection pool
│   ├── routers/                 # API endpoints
│   ├── schemas/                 # Pydantic models
│   └── services/                # Business logic
├── migrations/                  # Database migrations
│   ├── migrate.py               # Migration runner
│   └── versions/                # SQL migration files
├── infrastructure/docker/       # Dockerfiles
└── docs/                        # Documentation
```

## API Overview

V2 uses a **Unified Artifact Model** where all knowledge is stored as artifacts:

- **Tenant**: Multi-tenancy isolation (all calls need `X-Tenant-ID` header)
- **Artifact Type**: Vocabulary for artifact categories
- **Artifact**: Universal knowledge unit (documents, chunks, intents, decisions)
- **Relation Type**: Vocabulary for relationship types
- **Relation**: Knowledge graph edges between artifacts
- **Embedding**: Vector representations for semantic search
- **Provenance Event**: Immutable audit trail

### Quick API Test

```bash
# Create a tenant
curl -X POST http://localhost:38000/tenants \
  -H "Content-Type: application/json" \
  -d '{"shortname": "demo", "name": "Demo Tenant", "tenant_type": "environment"}'

# Response: {"id": 1, "shortname": "demo", ...}

# List artifact types (requires tenant header)
curl http://localhost:38000/artifact-types \
  -H "X-Tenant-ID: 1"
```

## Migrations

```bash
# Apply all pending migrations
docker compose exec api python -m migrations.migrate up

# Check migration status
docker compose exec api python -m migrations.migrate status

# Rollback last migration
docker compose exec api python -m migrations.migrate down
```

## Logs and Debugging

```bash
# View API logs
docker compose logs -f api

# View all logs
docker compose logs -f

# Check container status
docker compose ps -a
```

## V2 vs V1 Differences

| Aspect | V1 | V2 |
|--------|----|----|
| Entities | Intent, Decision, Artifact (separate) | Unified Artifact model |
| Tenant types | `user` | `environment`, `project`, `experiment` |
| Port (postgres) | 5432 | 35432 |
| Port (API) | 8000 | 38000 |
| Hot-reload | No | Yes (via override file) |
| Landing page | JSON | HTML with links |

## Documentation

- `docs/entity-guide.md` - Entity relationships and usage patterns
- `docs/api-design.md` - API design principles
- `docs/data-model.md` - Database schema
- `docs/architecture.md` - System architecture
- `docs/search-architecture.md` - Semantic search implementation
