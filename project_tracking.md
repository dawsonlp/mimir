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
- [x] Phase 4: Spans & Relations ✅
  - [x] Migration 005: spans table with span_type enum
  - [x] Migration 006: relations table with entity_type, relation_type enums
  - [x] Pydantic schemas (span.py, relation.py)
  - [x] Services (span_service.py, relation_service.py)
  - [x] API routers (/api/v1/spans, /api/v1/relations)
  - [x] Entity relations endpoint for graph queries
  - [x] Linting and tests passing
- [x] Phase 5: Search & Embeddings ✅
  - [x] Migration 007: embeddings table with vector(3072), embedding_model enum
  - [x] Full-text search columns (search_vector) added to artifacts and artifact_versions
  - [x] HNSW index for approximate nearest neighbor search (cosine similarity)
  - [x] GIN indexes for full-text search
  - [x] Pydantic schemas (embedding.py, search.py)
  - [x] Services (embedding_service.py, search_service.py)
  - [x] OpenAI embedding integration (text-embedding-3-small/large, ada-002)
  - [x] Semantic search with pgvector cosine distance
  - [x] Full-text search with tsvector/tsquery
  - [x] Hybrid search with Reciprocal Rank Fusion (RRF)
  - [x] Similar artifacts search
  - [x] API routers (/api/v1/search, /api/v1/embeddings)
  - [x] Configuration: OPENAI_API_KEY, DEFAULT_EMBEDDING_MODEL
  - [x] Linting and tests passing
- [x] Phase 6: Provenance & Polish ✅
  - [x] Migration 008: provenance_events table (append-only audit log)
  - [x] Enums: provenance_entity_type, provenance_action, provenance_actor_type
  - [x] Pydantic schemas (provenance.py)
  - [x] Services (provenance_service.py)
  - [x] API routers (/api/v1/provenance)
  - [x] Entity history queries
  - [x] Correlated event tracking
  - [x] Time-based and actor filtering
  - [x] Linting and tests passing

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

## Phase 4 API Summary

### Spans
- `POST /api/v1/spans` - Create span (quote, highlight, annotation)
- `GET /api/v1/spans` - List spans (paginated, filter by artifact/type)
- `GET /api/v1/spans/{id}` - Get span
- `PATCH /api/v1/spans/{id}` - Update span
- `DELETE /api/v1/spans/{id}` - Delete span

### Relations
- `POST /api/v1/relations` - Create relation between entities
- `GET /api/v1/relations` - List relations (paginated, filter by source/target/type)
- `GET /api/v1/relations/entity/{type}/{id}` - List all relations for an entity
- `GET /api/v1/relations/{id}` - Get relation
- `PATCH /api/v1/relations/{id}` - Update relation
- `DELETE /api/v1/relations/{id}` - Delete relation

### Span Types
- `quote` - Exact text selection
- `highlight` - Emphasized section
- `annotation` - Commentary on a section
- `reference` - Reference marker
- `bookmark` - Saved position

### Entity Types (for Relations)
- `artifact`, `artifact_version`, `intent`, `intent_group`, `decision`, `span`

### Relation Types
- `references` - Source references target
- `supports` - Source provides evidence for target
- `contradicts` - Source contradicts target
- `derived_from` - Source was created from target
- `supersedes` - Source replaces target
- `related_to` - General association
- `parent_of` / `child_of` - Hierarchical relationships
- `implements` - Source implements target (decision→intent)
- `resolves` - Source resolves target (decision→intent)

## Phase 5 API Summary

### Search
- `POST /api/v1/search` - Unified search (semantic, fulltext, or hybrid)
- `POST /api/v1/search/semantic` - Vector similarity search via pgvector
- `POST /api/v1/search/fulltext` - PostgreSQL full-text search
- `POST /api/v1/search/similar` - Find artifacts similar to a given artifact

### Embeddings
- `POST /api/v1/embeddings` - Create embedding for an artifact
- `POST /api/v1/embeddings/batch` - Batch create embeddings for multiple artifacts
- `GET /api/v1/embeddings` - List embeddings (paginated, filter by artifact/model)
- `GET /api/v1/embeddings/{id}` - Get embedding by ID
- `DELETE /api/v1/embeddings/{id}` - Delete embedding
- `DELETE /api/v1/embeddings/artifact/{id}` - Delete all embeddings for an artifact

### Embedding Models
- `openai-text-embedding-3-small` (1536 dimensions) - Default
- `openai-text-embedding-3-large` (3072 dimensions)
- `openai-text-embedding-ada-002` (1536 dimensions, legacy)
- `sentence-transformers-all-mpnet` (768 dimensions) - Future
- `sentence-transformers-all-minilm` (384 dimensions) - Future

### Search Types
- `semantic` - Vector similarity using cosine distance with HNSW index
- `fulltext` - PostgreSQL tsvector/tsquery with GIN index
- `hybrid` - Combined using Reciprocal Rank Fusion (RRF, k=60)

## Phase 6 API Summary

### Provenance Events
- `POST /api/v1/provenance` - Record a provenance event
- `GET /api/v1/provenance` - List events (paginated, filter by entity/action/actor/time)
- `GET /api/v1/provenance/entity/{type}/{id}` - Get provenance history for an entity
- `GET /api/v1/provenance/correlation/{id}` - Get all events with same correlation ID

### Provenance Entity Types
- `tenant`, `artifact`, `artifact_version`, `intent`, `intent_group`
- `decision`, `span`, `relation`, `embedding`

### Provenance Actions
- `create` - Entity created
- `update` - Entity modified
- `delete` - Entity removed
- `supersede` - Entity replaced by another
- `archive` - Entity archived
- `restore` - Entity restored from archive

### Provenance Actor Types
- `user` - Human user
- `system` - Automated system process
- `llm` - Large language model
- `api_client` - API client application
- `migration` - Database migration
