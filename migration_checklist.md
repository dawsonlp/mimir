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

- [x] **Create v2/docs/ structure** ✅

- [x] **overview.md** - Project vision ✅
  - [x] What Mímir is (and is not)
  - [x] Core goals and value proposition
  - [x] RAG comparison table
  - [x] Technology stack
  - [x] Non-goals and boundaries

- [x] **requirements.md** - V1-V3 roadmap ✅
  - [x] Version roadmap (Remember → Reflect → Synthesize)
  - [x] Core capabilities per version
  - [x] 10 storage system non-goals
  - [x] What storage may do (allowed capabilities)

- [x] **design-decisions.md** - Architectural decisions ✅
  - [x] DD-001 through DD-009
  - [x] DD-009: Unified Artifact Model (V2 key change)

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

- [x] **pyproject.toml** (port from V1) ✅
- [x] **docker-compose.yaml** (port from V1, update paths to v2/) ✅
- [x] **docker-compose.override.yaml** (port from V1) ✅
- [x] **infrastructure/docker/api/Dockerfile** (port from V1) ✅
- [x] **infrastructure/docker/postgres/Dockerfile** (port from V1) ✅
- [x] **init-scripts/01-create-extensions.sql** (port from V1) ✅
- [x] **.env.example** (port from V1) ✅
- [x] **.gitignore** and **.dockerignore** (port from V1) ✅
- [x] Test Docker Compose starts successfully ✅

---

## Phase 3: Database Schema

**Note:** V2 migrations are a clean, rationalized design from scratch — not V1's incremental changes. V1 had 10 migrations reflecting development history; V2 consolidates to 6 logical units.

- [x] Create v2/migrations/ structure ✅
- [x] **001_schema_and_tenant.up.sql** ✅
  - [x] Create `mimirdata` schema (idempotent)
  - [x] Create all enums (artifact_type, entity_type, relation_type, span_type, provenance_action, provenance_actor_type)
  - [x] Create tenant table with all columns from start
- [x] **002_artifact.up.sql** ✅
  - [x] artifact table with extended type enum (includes intent, decision, analysis, etc.)
  - [x] artifact_version table
  - [x] Full-text search columns (search_vector) from start
  - [x] source, source_system, external_id columns from start
  - [x] GIN indexes for FTS
  - [x] Triggers for auto-updating search_vector
- [x] **003_relation.up.sql** ✅
  - [x] relation table with unified entity_type enum (artifact, artifact_version, span only)
  - [x] All relation_type values from start
  - [x] Indexes for bidirectional queries
  - [x] Self-reference prevention constraint
- [x] **004_span.up.sql** ✅
  - [x] span table with all span_type values
  - [x] Indexes
  - [x] Valid offset constraint
- [x] **005_embedding.up.sql** ✅
  - [x] embedding table with vector(2000) (HNSW max limit)
  - [x] Model column as TEXT (not enum) for flexibility
  - [x] HNSW index for approximate nearest neighbor (cosine distance)
  - [x] Chunk metadata columns
- [x] **006_provenance.up.sql** ✅
  - [x] provenance_event table (append-only audit log)
  - [x] All provenance enums from start
  - [x] Indexes for entity lookups and time queries
- [x] **schema_migrations table** (created by migrate.py, not a migration file) ✅
  - [x] Tracks applied migrations
- [x] Create corresponding .down.sql files ✅
- [x] Create migrate.py runner (port from V1) ✅
- [x] Run migrations and verify schema created ✅

**Tables created:**
- `mimirdata.tenant`
- `mimirdata.artifact`
- `mimirdata.artifact_version`
- `mimirdata.relation`
- `mimirdata.span`
- `mimirdata.embedding`
- `mimirdata.provenance_event`
- `mimirdata.schema_migrations`

---

## Phase 4: Core Implementation

**Legend:** `port` = copy from V1 with minimal changes, `modify` = significant changes needed

- [ ] Create v2/src/mimir/ package structure
- [ ] **database.py** (port) - Connection pool
- [ ] **config.py** (port) - Settings
- [ ] **main.py** (modify) - Remove intent/decision router registrations

### Services
- [ ] **tenant_service.py** (port)
- [ ] **artifact_service.py** (modify) - Extended type enum, absorbs intent/decision patterns
- [ ] **relation_service.py** (modify) - Simplified entity_type enum
- [ ] **span_service.py** (port)
- [ ] **embedding_service.py** (port)
- [ ] **search_service.py** (modify) - Update entity_type references
- [ ] **provenance_service.py** (modify) - Update entity_type enum

### Routers
- [ ] **tenants.py** (port)
- [ ] **artifacts.py** (modify) - Extended type enum, /types endpoint
- [ ] **relations.py** (modify) - Simplified entity_type validation
- [ ] **spans.py** (port)
- [ ] **embeddings.py** (port)
- [ ] **search.py** (port)
- [ ] **provenance.py** (modify) - Update entity_type enum

### Schemas (Pydantic)
- [ ] **tenant.py** (port)
- [ ] **artifact.py** (modify) - Extended ArtifactType enum
- [ ] **relation.py** (modify) - Simplified EntityType enum
- [ ] **span.py** (port)
- [ ] **embedding.py** (port)
- [ ] **search.py** (port)
- [ ] **provenance.py** (modify) - Update entity_type references

### Embedding Providers (all port)
- [ ] **base.py**
- [ ] **registry.py**
- [ ] **voyage.py**
- [ ] **openai.py**
- [ ] **ollama.py**

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

## V1 Components Not in V2

These V1 files will not be recreated in V2 — their functionality is absorbed by the unified artifact model:

| V1 Component | V2 Equivalent |
|--------------|---------------|
| `intents.py` (router) | `/artifacts` with `artifact_type=intent` |
| `intent_service.py` | `artifact_service.py` |
| `intent.py` (schema) | `artifact.py` with intent type |
| `003_create_intents.up.sql` | Part of `002_artifacts.up.sql` (artifact_type enum) |
| `decisions.py` (router) | `/artifacts` with `artifact_type=decision` |
| `decision_service.py` | `artifact_service.py` |
| `decision.py` (schema) | `artifact.py` with decision type |
| `004_create_decisions.up.sql` | Part of `002_artifacts.up.sql` (artifact_type enum) |
| `intent_groups` table | Replaced by artifacts with relations |

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
| Phase 2: Infrastructure | **Complete** | ▓▓▓▓▓▓▓▓▓▓ 100% |
| Phase 3: Database Schema | **Complete** | ▓▓▓▓▓▓▓▓▓▓ 100% |
| Phase 4: Core Implementation | Not Started | ░░░░░░░░░░ 0% |
| Phase 5: Testing & Validation | Not Started | ░░░░░░░░░░ 0% |
| Phase 6: Final Replacement | Not Started | ░░░░░░░░░░ 0% |

**Last Updated**: December 28, 2025

**Note on Phase 3:** Used singular table names (artifact, not artifacts) per standard DB convention. HNSW index limited to 2000 dimensions (pgvector constraint).
