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

**Note:** V2 migrations are a clean, rationalized design from scratch — not V1's incremental changes. V1 had 10 migrations reflecting development history; V2 consolidates to 5 logical units.

**Key Schema Decision:** Vocabulary tables (not ENUMs) for extensible types. See `v2/docs/schema-review.md` for rationale.

- [x] Create v2/migrations/ structure ✅
- [x] **001_schema_and_tenant.up.sql** ✅
  - [x] Create `mimirdata` schema (idempotent)
  - [x] Create **vocabulary tables** (artifact_type, relation_type, tenant_type) with seed data
  - [x] Create **system ENUMs** (entity_type, provenance_action, provenance_actor_type)
  - [x] Create tenant table with FK to tenant_type
- [x] **002_artifact.up.sql** ✅
  - [x] artifact table with FK to artifact_type vocabulary
  - [x] artifact_version table
  - [x] Positional columns (start_offset, end_offset, position_metadata) for chunks/quotes
  - [x] Full-text search columns (search_vector) from start
  - [x] source, source_system, external_id columns from start
  - [x] GIN indexes for FTS
  - [x] Triggers for auto-updating updated_at
- [x] **003_relation.up.sql** ✅
  - [x] relation table with FK to relation_type vocabulary
  - [x] entity_type enum (artifact, artifact_version only - spans absorbed)
  - [x] Indexes for bidirectional queries
  - [x] Unique constraint preventing duplicates
- [x] **004_embedding.up.sql** ✅
  - [x] embedding table with vector(2000) (HNSW max limit)
  - [x] Model column as TEXT (not enum) for flexibility
  - [x] HNSW index for approximate nearest neighbor (cosine distance)
- [x] **005_provenance.up.sql** ✅
  - [x] provenance_event table (append-only audit log)
  - [x] Uses system ENUMs (provenance_action, provenance_actor_type)
  - [x] Indexes for entity lookups and time queries
- [x] **schema_migrations table** (created by migrate.py, not a migration file) ✅
  - [x] Tracks applied migrations
- [x] Create corresponding .down.sql files ✅
- [x] Create migrate.py runner (port from V1) ✅
- [x] Run migrations and verify schema created ✅

**Tables created:**
- `mimirdata.artifact_type` (vocabulary - 18 types)
- `mimirdata.relation_type` (vocabulary - 16 types with inverse_code)
- `mimirdata.tenant_type` (vocabulary - 3 types)
- `mimirdata.tenant`
- `mimirdata.artifact`
- `mimirdata.artifact_version`
- `mimirdata.relation`
- `mimirdata.embedding`
- `mimirdata.provenance_event`
- `mimirdata.schema_migrations`

**System ENUMs created:**
- `entity_type` (artifact, artifact_version)
- `provenance_action` (create, update, delete, supersede, archive, restore)
- `provenance_actor_type` (user, system, llm, api_client, migration)

---

## Phase 4: Core Implementation

**Legend:** `port` = copy from V1 with minimal changes, `modify` = significant changes needed

- [x] Create v2/src/mimir/ package structure ✅
- [x] **database.py** (port) - Connection pool ✅
- [x] **config.py** (port) - Settings ✅
- [x] **main.py** (modify) - All routers registered ✅

### Services
- [x] **tenant_service.py** (modify) - FK to tenant_type vocabulary ✅
- [x] **artifact_service.py** (modify) - FK to artifact_type vocabulary, absorbs intent/decision/span patterns ✅
- [x] **artifact_type_service.py** (new) - CRUD for artifact_type vocabulary ✅
- [x] **relation_service.py** (modify) - FK to relation_type vocabulary ✅
- [x] **relation_type_service.py** (new) - CRUD for relation_type vocabulary ✅
- [x] **embedding_service.py** (port) ✅
- [x] **search_service.py** (modify) - Update entity_type references ✅
- [x] **provenance_service.py** (modify) - Update entity_type enum ✅

### Routers
- [x] **tenants.py** (port) ✅
- [x] **artifacts.py** (modify) - FK validation, versions, hierarchy endpoints ✅
- [x] **artifact_types.py** (new) - CRUD for artifact_type vocabulary ✅
- [x] **relations.py** (modify) - FK validation, entity relations queries ✅
- [x] **relation_types.py** (new) - CRUD with inverse type lookup ✅
- [x] **embeddings.py** (port) - find_similar, delete_entity_embeddings ✅
- [x] **search.py** (port) - fulltext, semantic, hybrid, similar_artifacts ✅
- [x] **provenance.py** (modify) - Entity history, actor activity ✅

### Schemas (Pydantic)
- [x] **tenant.py** (modify) - tenant_type as TEXT ✅
- [x] **artifact.py** (modify) - artifact_type as TEXT, positional columns ✅
- [x] **artifact_type.py** (new) - Vocabulary schema ✅
- [x] **relation.py** (modify) - relation_type as TEXT ✅
- [x] **relation_type.py** (new) - Vocabulary schema with inverse_code ✅
- [x] **embedding.py** (port) ✅
- [x] **search.py** (port) ✅
- [x] **provenance.py** (modify) - Update entity_type references ✅

### Embedding Providers (all port)
- [x] **base.py** ✅
- [x] **registry.py** ✅
- [x] **openai.py** ✅
- [x] **ollama.py** ✅

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

- [x] Delete all V1 source files (`src/mimir/`, `migrations/`, etc.) ✅
- [x] Move `v2/src/` to `src/` ✅
- [x] Move `v2/migrations/` to `migrations/` ✅
- [x] Move `v2/infrastructure/` to `infrastructure/` ✅
- [x] Update root `pyproject.toml` (or move v2 version) ✅
- [x] Update root `docker-compose.yaml` (or move v2 version) ✅
- [x] Update root `README.md` for V2 ✅
- [x] Move `v2/docs/` content to root docs ✅
- [x] Delete empty `v2/` directory ✅
- [ ] Run full test suite to verify (Phase 5 - tests not yet written)
- [x] Final commit and push ✅

**End State:** Single project with V2 implementation at root level. No `v2/` directory.

**Completed:** December 28, 2025
**Commit:** d6a8a65 - refactor: migrate V2 unified artifact model to root

---

## V1 Components Not in V2

These V1 files will not be recreated in V2 — their functionality is absorbed by the unified artifact model:

| V1 Component | V2 Equivalent |
|--------------|---------------|
| `intents.py` (router) | `/artifacts` with `artifact_type=intent` |
| `intent_service.py` | `artifact_service.py` |
| `intent.py` (schema) | `artifact.py` with intent type |
| `003_create_intents.up.sql` | Part of `artifact_type` vocabulary |
| `decisions.py` (router) | `/artifacts` with `artifact_type=decision` |
| `decision_service.py` | `artifact_service.py` |
| `decision.py` (schema) | `artifact.py` with decision type |
| `004_create_decisions.up.sql` | Part of `artifact_type` vocabulary |
| `spans.py` (router) | `/artifacts` with positional types (chunk, quote, etc.) |
| `span_service.py` | `artifact_service.py` with start_offset/end_offset |
| `span.py` (schema) | `artifact.py` with positional columns |
| `005_create_spans.up.sql` | Columns in `002_artifacts.up.sql` |
| `intent_groups` table | `artifact_type=intent_group` with relations |

---

## Key Design Changes in V2

### Vocabulary Tables (Not ENUMs)

**Design Decision:** Extensible types use vocabulary tables with FK constraints for flexibility. System types stay as ENUMs for stability.

### Artifact Types (Vocabulary Table)

```sql
CREATE TABLE artifact_type (
    code TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    description TEXT,
    category TEXT,  -- 'content', 'positional', 'derived'
    is_active BOOLEAN DEFAULT true,
    sort_order INT
);
-- 18 seeded types including intent_group
```

| Category | Types |
|----------|-------|
| content | conversation, document, note |
| positional | chunk, quote, highlight, annotation, reference, bookmark |
| derived | intent, intent_group, decision, analysis, summary, conclusion, finding, question, answer |

### Relation Types (Vocabulary Table)

```sql
CREATE TABLE relation_type (
    code TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    inverse_code TEXT,      -- Links to inverse relation
    is_symmetric BOOLEAN,   -- true if A→B implies B→A
    ...
);
-- 16 seeded types with inverse relationships
```

| Relation | Inverse | Symmetric |
|----------|---------|-----------|
| references | referenced_by | no |
| supports | supported_by | no |
| contradicts | - | yes |
| derived_from | source_of | no |
| supersedes | superseded_by | no |
| related_to | - | yes |
| parent_of | child_of | no |
| implements | implemented_by | no |
| resolves | resolved_by | no |

### Entity Types (System ENUM - Fixed)

```sql
CREATE TYPE entity_type AS ENUM (
    'artifact',
    'artifact_version'
);
```

Note: Spans absorbed into artifacts as positional types (chunk, quote, etc.). No separate span entity.

### Spans Absorbed into Artifacts

V1 had a separate `span` table. V2 handles positional content as artifacts with:
- `artifact_type` = chunk, quote, highlight, annotation, etc.
- `parent_artifact_id` = reference to source artifact
- `start_offset`, `end_offset` = character positions
- `position_metadata` = JSONB for page, line, paragraph info

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
| Phase 4: Core Implementation | **Complete** | ▓▓▓▓▓▓▓▓▓▓ 100% |
| Phase 5: Testing & Validation | Not Started | ░░░░░░░░░░ 0% |
| Phase 6: Final Replacement | **Complete** | ▓▓▓▓▓▓▓▓▓▓ 100% |

**Last Updated**: December 28, 2025

**Phase 4 Summary:**
- 8 Pydantic schemas (tenant, artifact, artifact_type, relation, relation_type, embedding, search, provenance)
- 9 services including 2 new vocabulary services (artifact_type, relation_type)
- 8 routers including 2 new vocabulary routers
- 4 embedding provider files (base, registry, openai, ollama)
- FastAPI main.py with all routers registered

**Note on Phase 3:** Used singular table names (artifact, not artifacts) per standard DB convention. HNSW index limited to 2000 dimensions (pgvector constraint).
