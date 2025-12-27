# Project Tracking

## Issue Tracker

**Platform:** GitHub Issues  
**Repository:** https://github.com/dawsonlp/mimir

## Epic

**[EPIC] Mímir V1 - Foundation Implementation**  
*Issue to be created when repository is set up*

## Labels

| Label | Description | Color |
|-------|-------------|-------|
| `epic` | Large feature or initiative | Purple (#7057ff) |
| `phase-1` | Foundation phase | Blue |
| `phase-2` | Core entities phase | Green |
| `phase-3` | Intent & Decisions phase | Teal |

## Implementation Phases

- [x] Phase 1: Foundation - Project scaffolding, Docker Compose, database setup ✅
- [x] Phase 2: Core Entities - Artifacts model, versions, CRUD endpoints ✅
  - [x] Plain SQL migration system (replaced Alembic)
  - [x] Tenants table with SERIAL PK, shortname
  - [x] Artifacts table with SERIAL PK
  - [x] Artifact_versions table (append-only)
  - [x] Design decisions DD-003 (no ORM), DD-005 (SERIAL PKs)
  - [x] Pydantic schemas (tenant.py, artifact.py)
  - [x] Services (tenant_service.py, artifact_service.py)
  - [x] API routers (/api/v1/tenants, /api/v1/artifacts)
  - [x] Unit tests passing
- [x] Phase 3: Intent & Decisions ✅
  - [x] Migration 003: intent_groups and intents tables
  - [x] Migration 004: decisions table
  - [x] Enums: intent_status, intent_source, decision_status, decision_source
  - [x] Pydantic schemas (intent.py, decision.py)
  - [x] Services (intent_service.py, decision_service.py)
  - [x] API routers (/api/v1/intents, /api/v1/intent-groups, /api/v1/decisions)
  - [x] Decision supersede endpoint with chain tracking
  - [x] Linting and tests passing
- [ ] Phase 4: Spans & Relations - Spans, relations, traversal queries
- [ ] Phase 5: Search & Embeddings - pgvector, FTS, semantic search
- [ ] Phase 6: Provenance & Polish - Provenance recording, documentation

## Conventions

### Issue Titles
- `[EPIC]` - Large initiative with multiple sub-tasks
- `[FEAT]` - New feature
- `[FIX]` - Bug fix
- `[DOCS]` - Documentation update
- `[INFRA]` - Infrastructure/DevOps changes

### Commit Messages
Follow conventional commits:
- `feat:` - New feature
- `fix:` - Bug fix
- `docs:` - Documentation
- `refactor:` - Code refactoring
- `test:` - Tests
- `chore:` - Maintenance

## Environment Configuration

Environment-specific values are stored in `.env` (not committed to git).

See `.env.example` for the template with all required variables:
- `POSTGRES_PASSWORD` - Database password
- `DOCKER_BUILDX_BUILDER` - Docker BuildX builder name
- `LOG_LEVEL` - Application log level
- `ENVIRONMENT` - Deployment environment

## Phase 3 API Summary

### Intent Groups
- `POST /api/v1/intent-groups` - Create group
- `GET /api/v1/intent-groups` - List groups (paginated)
- `GET /api/v1/intent-groups/{id}` - Get group
- `PATCH /api/v1/intent-groups/{id}` - Update group
- `DELETE /api/v1/intent-groups/{id}` - Delete group

### Intents
- `POST /api/v1/intents` - Create intent
- `GET /api/v1/intents` - List intents (paginated, filter by status/group)
- `GET /api/v1/intents/{id}` - Get intent
- `PATCH /api/v1/intents/{id}` - Update intent
- `DELETE /api/v1/intents/{id}` - Delete intent

### Decisions
- `POST /api/v1/decisions` - Create decision
- `GET /api/v1/decisions` - List decisions (paginated, filter by status/intent/artifact)
- `GET /api/v1/decisions/{id}` - Get decision
- `PATCH /api/v1/decisions/{id}` - Update decision
- `DELETE /api/v1/decisions/{id}` - Delete decision
- `POST /api/v1/decisions/{id}/supersede` - Supersede with new decision
