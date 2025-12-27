# Project Tracking

## Issue Tracker

**Platform:** GitHub Issues  
**Repository:** *To be created*

## Epic

**[EPIC] Mímir V1 - Foundation Implementation**  
*Issue to be created when repository is set up*

## Labels

| Label | Description | Color |
|-------|-------------|-------|
| `epic` | Large feature or initiative | Purple (#7057ff) |
| `phase-1` | Foundation phase | Blue |
| `phase-2` | Core entities phase | Green |

## Implementation Phases

- [x] Phase 1: Foundation - Project scaffolding, Docker Compose, database setup ✅
- [ ] Phase 2: Core Entities - Artifacts model, versions, CRUD endpoints
  - [x] Plain SQL migration system (replaced Alembic)
  - [x] Tenants table with SERIAL PK, shortname
  - [x] Artifacts table with SERIAL PK
  - [x] Artifact_versions table (append-only)
  - [x] Design decisions DD-003 (no ORM), DD-005 (SERIAL PKs)
  - [ ] Pydantic schemas for API
  - [ ] CRUD endpoints
  - [ ] Unit tests for artifact service
- [ ] Phase 3: Intent & Decisions - Intents, intent groups, decisions
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
