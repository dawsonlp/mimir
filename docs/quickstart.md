# Mímir Quick Start

Get Mímir running in 5 minutes. No git clone required.

## Architecture

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  postgres   │────▶│   migrate   │────▶│     api     │
│  (database) │     │  (one-shot) │     │  (server)   │
└─────────────┘     └─────────────┘     └─────────────┘
     │                    │                    │
     │                    │                    │
  healthy ────────▶ runs migrations ───▶ starts server
                    then exits
```

**Startup sequence:**
1. `postgres` starts and becomes healthy
2. `migrate` runs database migrations (idempotent), then exits
3. `api` starts only after migrate succeeds

All images are pulled from Docker Hub. No build required.

## 1. Create Directory

```bash
mkdir mimir && cd mimir
```

## 2. Create docker-compose.yaml

```bash
cat > docker-compose.yaml << 'EOF'
services:
  postgres:
    image: dawsonlp/mimir-postgres:v1.0
    ports:
      - "35432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql
      - ./init-scripts:/docker-entrypoint-initdb.d:ro
    environment:
      POSTGRES_DB: mimir
      POSTGRES_USER: mimir
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U mimir -d mimir"]
      interval: 10s
      timeout: 5s
      retries: 5

  migrate:
    image: dawsonlp/mimir-api:v1.0
    environment:
      DATABASE_URL: postgresql://mimir:${POSTGRES_PASSWORD}@postgres:5432/mimir
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    depends_on:
      postgres:
        condition: service_healthy
    command: ["python", "-m", "migrations.migrate", "up"]
    restart: "no"

  api:
    image: dawsonlp/mimir-api:v1.0
    ports:
      - "38000:8000"
    environment:
      DATABASE_URL: postgresql://mimir:${POSTGRES_PASSWORD}@postgres:5432/mimir
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    depends_on:
      postgres:
        condition: service_healthy
      migrate:
        condition: service_completed_successfully

volumes:
  postgres_data:
EOF
```

## 3. Create Init Script

```bash
mkdir -p init-scripts
cat > init-scripts/01-create-extensions.sql << 'EOF'
CREATE SCHEMA IF NOT EXISTS mimirdata;
ALTER DATABASE mimir SET search_path TO mimirdata, public;
CREATE EXTENSION IF NOT EXISTS vector SCHEMA mimirdata;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
EOF
```

## 4. Create .env

```bash
echo "POSTGRES_PASSWORD=$(openssl rand -base64 24)" > .env
```

## 5. Start Services

```bash
docker compose up -d
```

Wait for healthy:
```bash
docker compose ps   # Should show "healthy"
```

## 6. Verify

```bash
curl http://localhost:38000/health/ready
```

## 7. Register Embedding Types (Required for Semantic Search)

Embedding types are **not seeded automatically** — they depend on which embedding
models are available in your environment. You must register them before creating
embeddings or using semantic/hybrid search.

> **Important:** If you skip this step, embedding creation will fail with
> `400: Embedding type 'xxx' not found or inactive`. This is by design — Mimir
> validates that the embedding type exists before accepting any vectors.

```bash
# Register nomic-embed-text (Ollama, 768 dimensions)
curl -X POST http://localhost:38000/embedding-types \
  -H "Content-Type: application/json" \
  -d '{
    "code": "nomic-embed-text",
    "display_name": "Nomic Embed Text",
    "provider": "ollama",
    "dimensions": 768
  }'
```

This creates the `embedding_type` registry entry **and** the underlying vector table
with HNSW index. You only need to do this once per environment (survives restarts,
but not `docker compose down -v`).

**Common embedding types:**

| Code | Provider | Dimensions | Registration |
|------|----------|------------|--------------|
| `nomic-embed-text` | Ollama | 768 | See above |
| `text-embedding-3-small` | OpenAI | 1536 | Requires `OPENAI_API_KEY` |
| `voyage-3` | Voyage AI | 1024 | Requires `VOYAGEAI_MIMIR_EMBEDDINGS` |

Verify registered types:
```bash
curl http://localhost:38000/embedding-types
```

## 8. Create First Artifact

```bash
curl -X POST http://localhost:38000/artifacts \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: 1" \
  -d '{"artifact_type": "note", "title": "Hello", "content": "First artifact!"}'
```

## Ports

| Service | Port |
|---------|------|
| API | localhost:38000 |
| PostgreSQL | localhost:35432 |

## API Docs

http://localhost:38000/docs

## Optional: Change Events

Mimir v5.5 can publish committed artifact, relation, and embedding creates to
Kafka through a separate publisher process. The base quickstart stack above does
not include Kafka, so change delivery is not active in this minimal setup.

If you run Mimir under larnet or another environment with Kafka, start the
publisher after migrations complete:

```bash
python -m mimir.outbox_publisher
```

Required publisher environment:

- `DATABASE_URL`
- `POSTGRES_PASSWORD`
- `KAFKA_BOOTSTRAP_SERVERS`
- `MIMIR_CHANGE_TOPIC` (defaults to `mimir.changes.v1`)

See [change-events.md](change-events.md) for the event contract, delivery
semantics, and consumer offset requirements.

## Stop

```bash
docker compose down      # Keep data
docker compose down -v   # Delete data
```

## Upgrades

To upgrade to a new version:

```bash
# Pull new images
docker compose pull

# Restart (migrate runs automatically for new migrations)
docker compose up -d
```

The migrate service is idempotent - it tracks applied migrations in `mimirdata.schema_migrations` and only runs pending ones.

## Troubleshooting

**Check service status:**
```bash
docker compose ps
docker compose logs migrate   # See migration output
docker compose logs api       # See API logs
```

**Migration failed:**
```bash
# View migration logs
docker compose logs migrate

# Re-run migrations manually
docker compose run --rm migrate
```

**Reset everything:**
```bash
docker compose down -v   # Removes data volume
docker compose up -d     # Fresh start
```

## Data Persistence

Data is stored in a Docker named volume (`postgres_data`):
- Survives container restarts and upgrades
- Located at `/var/lib/docker/volumes/mimir_postgres_data`
- Backed up via standard Docker volume backup methods

## Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `POSTGRES_PASSWORD` | Database password | **Required** |
| `LOG_LEVEL` | API log level | INFO |
| `OLLAMA_BASE_URL` | Ollama endpoint for embeddings | http://host.docker.internal:11434 |
| `DEFAULT_EMBEDDING_MODEL` | Embedding model | nomic-embed-text |
| `OPENAI_API_KEY` | OpenAI key for embeddings | (optional) |

Add variables to `.env`:
```bash
echo "LOG_LEVEL=DEBUG" >> .env
```
