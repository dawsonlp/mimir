# Mímir V2 Migration Checklist

This document tracks the complete rebuild of Mímir with a unified artifact model.

## Motivation

V1 implemented separate tables for Intent and Decision, creating:
- Table proliferation (each concept = table + service + router)
- Fragmented queries across entity types
- Ontological commitment before domain is fully understood

V2 consolidates all knowledge types into the Artifact abstraction, using Relations for connections and extended artifact_type enum for type discrimination.

---

## Phase 1: Documentation

- [x] **Create v2/ directory structure** ✅
  ```
  v2/
  ├── docs/
  │   ├── architecture.md
  │   ├── data-model.md
  │   ├── api-design.md
  │   └── search-architecture.md
  ├── src/
  ├── migrations/
  └── infrastructure/
  ```

- [x] **architecture.md** - Core principles ✅
  - [x] Unified artifact model (all knowledge = artifacts)
  - [x] Relations as the universal connection layer
  - [x] Spans for positional annotations
  - [x] Embeddings for vector search
  - [x] Provenance for audit trail
  - [x] Multi-tenant architecture

- [x] **data-model.md** - Database schema ✅
  - [x] Tenants table (unchanged from V1)
  - [x] Artifacts table with extended type enum
  - [x] Artifact_versions table (append-only)
  - [x] Relations table (polymorphic connections)
  - [x] Spans table (positional annotations)
  - [x] Embeddings table (vector storage)
  - [x] Provenance_events table (audit log)
  - [x] Entity type enum consolidation
  - [x] Artifact type enum (full list)
  - [x] Relation type enum (full list)

- [x] **api-design.md** - REST API specification ✅
  - [x] Artifacts CRUD endpoints
  - [x] Artifact types endpoint (list valid types)
  - [x] Relations endpoints
  - [x] Spans endpoints
  - [x] Embeddings endpoints
  - [x] Search endpoints (semantic, fulltext, hybrid)
  - [x] Provenance endpoints
  - [x] Query patterns for derived knowledge
  - [x] Request/response schemas

- [x] **search-architecture.md** - Search capabilities ✅
  - [x] RRF hybrid search algorithm
  - [x] Semantic search via pgvector
  - [x] Full-text search via tsvector
  - [x] Embedding provider abstraction
  - [x] Voyage AI, OpenAI, Ollama support
  - [x] Chunking strategy (client-side)

---

## Phase 2: Infrastructure

- [ ] **pyproject.toml** (port from V1)
- [ ] **docker-compose.yaml** (port from V1, update paths to v2/)
- [ ] **docker-compose.override.yaml** (port from V1)
- [ ] **infrastructure/docker/api/Dockerfile** (port from V1)
- [ ] **infrastructure/docker/postgres/Dockerfile** (port from V1)
- [ ] **init-scripts/01-create-extensions.sql** (port from V1)
- [ ] **.env.example** (port from V1)
- [ ] **.gitignore** and **.dockerignore** (port from V1)
- [ ] Test Docker Compose starts successfully

---

## Phase 3: Database Schema

- [ ] Create v2/migrations/ structure
- [ ] **001_create_tenants.up.sql** (port from V1)
- [ ] **002_create_artifacts.up.sql** (extended type enum)
- [ ] **003_create_relations.up.sql** (unified entity types)
- [ ] **004_create_spans.up.sql** (port from V1)
- [ ] **005_create_embeddings.up.sql** (port from V1)
- [ ] **006_create_provenance.up.sql** (port from V1)
- [ ] Create corresponding .down.sql files
- [ ] Create migrate.py runner (port from V1)
- [ ] Run migrations and verify schema created

---

## Phase 4: Core Implementation

- [ ] Create v2/src/mimir/ package structure
- [ ] **database.py** - Connection pool (port from V1)
- [ ] **config.py** - Settings (port from V1)
- [ ] **main.py** - FastAPI application

### Services
- [ ] **tenant_service.py** (port from V1)
- [ ] **artifact_service.py** (consolidated, no intent/decision services)
- [ ] **relation_service.py** (port from V1)
- [ ] **span_service.py** (port from V1)
- [ ] **embedding_service.py** (port from V1)
- [ ] **search_service.py** (port from V1)
- [ ] **provenance_service.py** (port from V1)

### Routers
- [ ] **tenants.py** (port from V1)
- [ ] **artifacts.py** (consolidated, handles all artifact types)
- [ ] **relations.py** (port from V1)
- [ ] **spans.py** (port from V1)
- [ ] **embeddings.py** (port from V1)
- [ ] **search.py** (port from V1)
- [ ] **provenance.py** (port from V1)

### Schemas (Pydantic)
- [ ] **tenant.py** (port from V1)
- [ ] **artifact.py** (extended type enum)
- [ ] **relation.py** (unified entity types)
- [ ] **span.py** (port from V1)
- [ ] **embedding.py** (port from V1)
- [ ] **search.py** (port from V1)
- [ ] **provenance.py** (port from V1)

### Embedding Providers
- [ ] **base.py** (port from V1)
- [ ] **registry.py** (port from V1)
- [ ] **voyage.py** (port from V1)
- [ ] **openai.py** (port from V1)
- [ ] **ollama.py** (port from V1)

---

## Phase 5: Testing & Validation

- [ ] Create tests/ structure
- [ ] Unit tests for services
- [ ] Integration tests for API
- [ ] Verify hybrid search works
- [ ] Verify embedding providers work
- [ ] Run ruff check
- [ ] Run pytest

---

## Phase 6: Final Replacement & Cleanup

Once V2 is validated and working:

- [ ] Delete all V1 source files (`src/mimir/`, `migrations/`, etc.)
- [ ] Move `v2/src/` to `src/`
- [ ] Move `v2/migrations/` to `migrations/`
- [ ] Move `v2/infrastructure/` to `infrastructure/`
- [ ] Update root `pyproject.toml` (or move v2 version)
- [ ] Update root `docker-compose.yaml` (or move v2 version)
- [ ] Update root `README.md` for V2
- [ ] Move `v2/docs/` content to root docs
- [ ] Delete empty `v2/` directory
- [ ] Run full test suite to verify
- [ ] Final commit and push

**End State:** Single project with V2 implementation at root level. No `v2/` directory.

---

## V1 Files to Remove (from V2)

| V1 File | V2 Status |
|---------|-----------|
| `intents.py` (router) | Removed - handled by artifacts |
| `intent_service.py` | Removed - handled by artifacts |
| `intent.py` (schema) | Removed - handled by artifacts |
| `003_create_intents.up.sql` | Removed |
| `decisions.py` (router) | Removed - handled by artifacts |
| `decision_service.py` | Removed - handled by artifacts |
| `decision.py` (schema) | Removed - handled by artifacts |
| `004_create_decisions.up.sql` | Removed |

---

## Key Design Changes in V2

### Artifact Types (Extended Enum)

```sql
CREATE TYPE artifact_type AS ENUM (
    -- Raw content
    'conversation',
    'document', 
    'note',
    'chunk',
    -- Derived knowledge
    'intent',
    'decision',
    'analysis',
    'summary',
    'conclusion',
    'finding',
    'question',
    'answer'
);
```

### Entity Types (Simplified)

```sql
CREATE TYPE entity_type AS ENUM (
    'artifact',
    'artifact_version',
    'span'
);
```

Note: `intent`, `intent_group`, and `decision` are now artifact types, not separate entity types.

### Relation Types (Unchanged)

```sql
CREATE TYPE relation_type AS ENUM (
    'references',
    'supports',
    'contradicts',
    'derived_from',
    'supersedes',
    'related_to',
    'parent_of',
    'child_of',
    'implements',
    'resolves'
);
```

### Common Patterns for Derived Knowledge

**Creating a decision:**
```json
POST /api/v1/artifacts
{
  "artifact_type": "decision",
  "title": "Use PostgreSQL for storage",
  "content": "We decided to use PostgreSQL 18 with pgvector...",
  "source": "user",
  "metadata": {
    "status": "active",
    "rationale": "Best combination of SQL + vector capabilities"
  }
}
```

**Linking decision to intent:**
```json
POST /api/v1/relations
{
  "source_type": "artifact",
  "source_id": 101,  // decision
  "target_type": "artifact", 
  "target_id": 100,  // intent
  "relation_type": "resolves"
}
```

**Linking decision to source conversation:**
```json
POST /api/v1/relations
{
  "source_type": "artifact",
  "source_id": 101,  // decision
  "target_type": "artifact",
  "target_id": 50,   // conversation
  "relation_type": "derived_from"
}
```

---

## Progress Tracking

| Phase | Status | Progress |
|-------|--------|----------|
| Phase 1: Documentation | **Complete** | ▓▓▓▓▓▓▓▓▓▓ 100% |
| Phase 2: Infrastructure | Not Started | ░░░░░░░░░░ 0% |
| Phase 3: Database Schema | Not Started | ░░░░░░░░░░ 0% |
| Phase 4: Core Implementation | Not Started | ░░░░░░░░░░ 0% |
| Phase 5: Testing & Validation | Not Started | ░░░░░░░░░░ 0% |
| Phase 6: Documentation & Cleanup | Not Started | ░░░░░░░░░░ 0% |

**Last Updated**: December 28, 2025
