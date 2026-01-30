# Mímir Quick Start

Get Mímir running in 5 minutes.

## 1. Setup

```bash
cd backend

# Create environment file
echo "POSTGRES_PASSWORD=$(openssl rand -base64 24)" > .env
```

## 2. Start Services

```bash
docker compose up -d
```

Wait for healthy status:
```bash
docker compose ps
```

## 3. Run Migrations

```bash
docker compose exec api python -m migrations.migrate up
```

## 4. Verify

```bash
curl http://localhost:38000/health/ready
# {"status":"ok","database":"connected"}
```

## 5. Create First Artifact

```bash
curl -X POST http://localhost:38000/artifacts \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: 1" \
  -d '{"artifact_type": "note", "title": "Hello Mímir", "content": "First artifact!"}'
```

## Ports

| Service | Port |
|---------|------|
| API | `localhost:38000` |
| PostgreSQL | `localhost:35432` |

## Stop

```bash
docker compose down        # Keep data
docker compose down -v     # Delete data
```

## API Docs

http://localhost:38000/docs