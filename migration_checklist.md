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

- [ ] **Create v2/ directory structure**
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

- [ ] **architecture.md** - Core principles
  - [ ] Unified artifact model (all knowledge = artifacts)
  - [ ] Relations as the universal connection layer
  - [ ] Spans for positional annotations
  - [ ] Embeddings for vector search
  - [ ] Provenance for audit trail
  - [ ] Multi-tenant architecture

- [ ] **data-model.md** - Database schema
  - [ ] Tenants table (unchanged from V1)
  - [ ] Artifacts table with extended type enum
  - [ ] Artifact_versions table (append-only)
  - [ ] Relations table (polymorphic connections)
  - [ ] Spans table (positional annotations)
  - [ ] Embeddings table (vector storage)
  - [ ] Provenance_events table (audit log)
  - [ ] Entity type enum consolidation
  - [ ] Artifact type enum (full list)
  - [ ] Relation type enum (full list)

- [ ] **api-design.md** - REST API specification
  - [ ] Artifacts CRUD endpoints
  - [ ] Artifact types endpoint (list valid types)
  - [ ] Relations endpoints
  - [ ] Spans endpoints
  - [ ] Embeddings endpoints
  - [ ] Search endpoints (semantic, fulltext, hybrid)
  - [ ] Provenance endpoints
  - [ ] Query patterns for derived knowledge
  - [ ] Request/response schemas

- [ ] **search-architecture.md** - Search capabilities
  - [ ] RRF hybrid search algorithm
  - [ ] Semantic search via pgvector
  - [ ] Full-text search via tsvector
  - [ ] Embedding provider abstraction
  - [ ] Voyage AI, OpenAI, Ollama support
  - [ ] Chunking strategy (client-side)

---

## Phase 2: Database Schema

- [ ] Create v2/migrations/ structure
- [ ] **001_create_tenants.up.sql** (port from V1)
- [ ] **002_create_artifacts.up.sql** (extended type enum)
- [ ] **003_create_relations.up.sql** (unified entity types)
- [ ] **004_create_spans.up.sql** (port from V1)
- [ ] **005_create_embeddings.up.sql** (port from V1)
- [ ] **006_create_provenance.up.sql** (port from V1)
- [ ] Create corresponding .down.sql files
- [ ] Create migrate.py runner (port from V1)

---

## Phase 3: Core Implementation

- [ ] Create v2/src/mimir/ package structure
- [ ] **database.py** - Connection pool (port from V1)
- [ ] **config.py** - Settings (port from V1)

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

## Phase 4: Infrastructure

- [ ] **docker-compose.yaml** (port from V1, update paths)
- [ ] **infrastructure/docker/api/Dockerfile** (port from V1)
- [ ] **infrastructure/docker/postgres/Dockerfile** (port from V1)
- [ ] **init-scripts/01-create-extensions.sql** (port from V1)
- [ ] **pyproject.toml** (port from V1)
- [ ] **.env.example** (port from V1)

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

## Phase 6: Documentation & Cleanup

- [ ] Update README.md for V2
- [ ] Update design_decisions.md with DD-009 (Unified Artifact Model)
- [ ] Archive V1 reference (or remove)
- [ ] Final commit and push

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
| Phase 1: Documentation | Not Started | ░░░░░░░░░░ 0% |
| Phase 2: Database Schema | Not Started | ░░░░░░░░░░ 0% |
| Phase 3: Core Implementation | Not Started | ░░░░░░░░░░ 0% |
| Phase 4: Infrastructure | Not Started | ░░░░░░░░░░ 0% |
| Phase 5: Testing | Not Started | ░░░░░░░░░░ 0% |
| Phase 6: Documentation | Not Started | ░░░░░░░░░░ 0% |

**Last Updated**: December 28, 2025
