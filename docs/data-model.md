# Mímir V3 Data Model

## Schema

All tables live in the `mimirdata` schema.

## Core Principles

| Principle | Implementation |
|-----------|----------------|
| **Each artifact is its own identity** | UUIDv7 primary keys, no version tables |
| **Append-only** | INSERT only on content tables (artifact, relation, embedding, provenance) |
| **Client-generated UUIDs** | Optional on create; server generates UUIDv7 if omitted |
| **No mutations** | No UPDATE on content tables |
| **No deletes** | No DELETE on content tables (for now) |
| **Supersedes = editorial intent** | Just a relation type, not identity equivalence |

## Tables

### Vocabulary Tables (Admin - Mutable)

These configuration tables support full CRUD operations.

#### tenant_type

| Column | Type | Description |
|--------|------|-------------|
| code | TEXT PK | Unique identifier |
| display_name | TEXT | Human-readable name |
| description | TEXT | Optional description |
| is_active | BOOLEAN | Soft disable flag |
| sort_order | INT | Display ordering |
| created_at | TIMESTAMPTZ | Creation timestamp |

#### artifact_type

| Column | Type | Description |
|--------|------|-------------|
| code | TEXT PK | Unique identifier (conversation, document, chunk, etc.) |
| display_name | TEXT | Human-readable name |
| description | TEXT | Optional description |
| category | TEXT | Grouping: content, positional, derived |
| is_active | BOOLEAN | Soft disable flag |
| sort_order | INT | Display ordering |
| created_at | TIMESTAMPTZ | Creation timestamp |

**Categories:**
- **content**: conversation, document, note (primary source material)
- **positional**: chunk, quote, highlight, annotation, reference, bookmark (positions within content)
- **derived**: intent, intent_group, decision, analysis, summary, conclusion, finding, question, answer

#### relation_type

| Column | Type | Description |
|--------|------|-------------|
| code | TEXT PK | Unique identifier |
| display_name | TEXT | Human-readable name |
| description | TEXT | Optional description |
| inverse_code | TEXT | Code of inverse relation (optional) |
| is_symmetric | BOOLEAN | True if A→B implies B→A |
| is_active | BOOLEAN | Soft disable flag |
| sort_order | INT | Display ordering |
| created_at | TIMESTAMPTZ | Creation timestamp |

**Seed relation types:**
- references / referenced_by
- supports / supported_by
- contradicts (symmetric)
- derived_from / source_of
- supersedes / superseded_by
- related_to (symmetric)
- parent_of / child_of
- implements / implemented_by
- resolves / resolved_by

---

### tenant (Admin - Mutable)

Multi-tenant isolation. Each tenant represents a logical partition.

| Column | Type | Description |
|--------|------|-------------|
| id | SERIAL PK | Internal identifier |
| shortname | TEXT UNIQUE | URL-safe identifier (e.g., "production") |
| name | TEXT | Display name |
| tenant_type | TEXT FK | Reference to tenant_type.code |
| description | TEXT | Optional description |
| is_active | BOOLEAN | Soft delete flag |
| created_at | TIMESTAMPTZ | Creation timestamp |
| metadata | JSONB | Extensible properties |

---

### artifact (Append-Only)

All content—raw and derived—is stored here with type discrimination.

| Column | Type | Description |
|--------|------|-------------|
| id | UUID PK | Client-generated UUIDv7 or server-generated |
| tenant_id | INT FK | Reference to tenant.id |
| artifact_type | TEXT FK | Reference to artifact_type.code |
| parent_artifact_id | UUID FK | Parent artifact for hierarchy (optional) |
| start_offset | INT | Character position start (for positional types) |
| end_offset | INT | Character position end (for positional types) |
| position_metadata | JSONB | Page, line, paragraph info (for positional types) |
| title | TEXT | Optional title/label |
| content | TEXT | Main content |
| content_hash | TEXT | SHA-256 hash for queries (not enforced unique) |
| source | TEXT | Origin category: import, manual, generated |
| source_system | TEXT | External system name: chatgpt, notion, github |
| external_id | TEXT | ID in source system |
| search_vector | TSVECTOR | Full-text search index (generated) |
| created_at | TIMESTAMPTZ | Creation timestamp |
| metadata | JSONB | Type-specific extensible properties |

**Constraints:**
- UNIQUE (tenant_id, source_system, external_id) WHERE external_id IS NOT NULL

**Note:** Positional artifact types (chunk, quote, highlight, etc.) use parent_artifact_id to reference their source artifact, plus start_offset/end_offset for character positions.

---

### relation (Append-Only)

Connections between artifacts.

| Column | Type | Description |
|--------|------|-------------|
| id | UUID PK | Client-generated or server-generated |
| tenant_id | INT FK | Reference to tenant.id |
| source_id | UUID FK | Source artifact |
| target_id | UUID FK | Target artifact |
| relation_type | TEXT FK | Reference to relation_type.code |
| confidence | FLOAT | Confidence score 0.0-1.0 (for LLM-proposed relations) |
| created_at | TIMESTAMPTZ | Creation timestamp |
| metadata | JSONB | Extensible properties |

**Constraints:**
- UNIQUE (tenant_id, source_id, target_id, relation_type)

---

### embedding (Append-Only)

Vector representations for semantic search.

| Column | Type | Description |
|--------|------|-------------|
| id | UUID PK | Server-generated |
| tenant_id | INT FK | Reference to tenant.id |
| artifact_id | UUID FK | Reference to artifact.id |
| model | TEXT | Embedding model name (voyage-3, text-embedding-3-small, nomic-embed-text) |
| dimensions | INT | Actual vector dimensions |
| embedding | VECTOR(2000) | pgvector column (HNSW max 2000 dims) |
| created_at | TIMESTAMPTZ | Creation timestamp |
| metadata | JSONB | Extensible properties |

**Indexes:** HNSW for approximate nearest neighbor search with cosine distance.

---

### provenance_event (Append-Only)

Audit log for all changes.

| Column | Type | Description |
|--------|------|-------------|
| id | UUID PK | Server-generated |
| tenant_id | INT FK | Reference to tenant.id |
| entity_type | TEXT | Type of entity: artifact, relation, embedding |
| entity_id | UUID | ID of the affected entity |
| action | TEXT | Action performed: create |
| actor_type | TEXT | Who performed: user, system, llm, api_client, migration |
| actor_id | TEXT | Actor identifier |
| reason | TEXT | Why the action was taken |
| created_at | TIMESTAMPTZ | When the action occurred |
| metadata | JSONB | Action-specific details |

---

## Indexes

| Table | Index Type | Purpose |
|-------|------------|---------|
| artifact | B-tree | tenant_id, artifact_type, source, source_system, created_at |
| artifact | B-tree | content_hash (for duplicate queries) |
| artifact | B-tree | external_id (unique per tenant+source_system) |
| artifact | B-tree | parent_artifact_id |
| artifact | GIN | search_vector (full-text search) |
| relation | B-tree | source_id, target_id, relation_type |
| embedding | HNSW | embedding vector (cosine similarity) |
| provenance_event | B-tree | entity_type/id, created_at |

## What Changed from V1

| V1 | V2 |
|----|----|
| SERIAL INT primary keys | UUID primary keys (UUIDv7) |
| artifact_version table | Removed - each artifact is its own identity |
| spans table | Merged into artifact (positional types) |
| entity_type enum | Simplified - relations only between artifacts |
| UPDATE/DELETE endpoints | Removed on content tables |
| Mutable artifacts | Append-only - no mutations |
