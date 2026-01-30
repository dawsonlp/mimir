# Mímir Quick Start

Get Mímir running in 5 minutes. No git clone required.

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

## 6. Run Migrations

```bash
docker compose exec api python -m migrations.migrate up
```

## 7. Verify

```bash
curl http://localhost:38000/health/ready
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

## Stop

```bash
docker compose down      # Keep data
docker compose down -v   # Delete data
```
