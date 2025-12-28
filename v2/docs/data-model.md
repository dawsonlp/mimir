# Mímir V2 Data Model

## Schema

All tables live in the `mimirdata` schema.

## Tables

### tenants

Multi-tenant isolation. Each tenant represents a logical partition (environment, project, or experiment).

| Column | Type | Description |
|--------|------|-------------|
| id | SERIAL | Primary key |
| shortname | TEXT | Unique identifier (e.g., "production") |
| name | TEXT | Display name |
| tenant_type | ENUM | environment, project, experiment |
| description | TEXT | Optional description |
| is_active | BOOLEAN | Soft delete flag |
| created_at | TIMESTAMPTZ | Creation timestamp |
| metadata | JSONB | Extensible properties |

---

### artifacts

All content—raw and derived—is stored here with type discrimination.

| Column | Type | Description |
|--------|------|-------------|
| id | SERIAL | Primary key |
| tenant_id | INT | FK to tenants |
| artifact_type | ENUM | See artifact types below |
| external_id | TEXT | Original source ID (e.g., ChatGPT conversation ID) |
| source | TEXT | Origin category (import, api, user, derived) |
| source_system | TEXT | External system name (chatgpt, confluence, github) |
| title | TEXT | Optional title/summary |
| created_at | TIMESTAMPTZ | Creation timestamp |
| updated_at | TIMESTAMPTZ | Last update timestamp |
| metadata | JSONB | Type-specific fields (status, rationale, etc.) |
| search_vector | TSVECTOR | Full-text search index |

**Artifact Types (V2 Extended):**
- Raw content: conversation, document, note, chunk
- Derived knowledge: intent, decision, analysis, summary, conclusion, finding, question, answer

---

### artifact_versions

Append-only content history. Content is never overwritten, only versioned.

| Column | Type | Description |
|--------|------|-------------|
| id | SERIAL | Primary key |
| artifact_id | INT | FK to artifacts |
| version_number | INT | Sequential version (1, 2, 3...) |
| content | TEXT | Full content for this version |
| content_hash | TEXT | SHA-256 for deduplication |
| created_at | TIMESTAMPTZ | Version creation timestamp |
| created_by | TEXT | User or system that created this version |

---

### relations

Polymorphic connections between any two entities.

| Column | Type | Description |
|--------|------|-------------|
| id | SERIAL | Primary key |
| tenant_id | INT | FK to tenants |
| source_type | ENUM | Entity type of source |
| source_id | INT | ID of source entity |
| target_type | ENUM | Entity type of target |
| target_id | INT | ID of target entity |
| relation_type | ENUM | Type of relationship |
| description | TEXT | Optional description |
| confidence | REAL | Confidence score (0.0-1.0) for LLM-proposed |
| created_at | TIMESTAMPTZ | Creation timestamp |
| updated_at | TIMESTAMPTZ | Last update timestamp |
| metadata | JSONB | Extensible properties |

**Entity Types (V2 Simplified):**
- artifact, artifact_version, span

**Relation Types:**
- references, supports, contradicts
- derived_from, supersedes, related_to
- parent_of, child_of
- implements, resolves

---

### spans

Positional annotations within artifact content.

| Column | Type | Description |
|--------|------|-------------|
| id | SERIAL | Primary key |
| tenant_id | INT | FK to tenants |
| artifact_id | INT | FK to artifacts |
| artifact_version_id | INT | Optional FK to specific version |
| span_type | ENUM | quote, highlight, annotation, reference, bookmark |
| start_offset | INT | Character position start |
| end_offset | INT | Character position end |
| content | TEXT | The selected/annotated text |
| annotation | TEXT | Optional commentary |
| created_at | TIMESTAMPTZ | Creation timestamp |
| updated_at | TIMESTAMPTZ | Last update timestamp |
| metadata | JSONB | Extensible properties |

---

### embeddings

Vector representations for semantic search.

| Column | Type | Description |
|--------|------|-------------|
| id | SERIAL | Primary key |
| tenant_id | INT | FK to tenants |
| artifact_id | INT | FK to artifacts |
| artifact_version_id | INT | Optional FK to specific version |
| model | TEXT | Embedding model name (voyage-3, text-embedding-3-small) |
| dimensions | INT | Vector dimensions |
| embedding | VECTOR | pgvector column |
| chunk_index | INT | Optional chunk position |
| chunk_text | TEXT | Optional chunk content |
| created_at | TIMESTAMPTZ | Creation timestamp |
| metadata | JSONB | Extensible properties |

**Indexes:** HNSW for approximate nearest neighbor search.

---

### provenance_events

Append-only audit log for all changes.

| Column | Type | Description |
|--------|------|-------------|
| id | SERIAL | Primary key |
| tenant_id | INT | FK to tenants |
| entity_type | ENUM | Type of entity affected |
| entity_id | INT | ID of entity affected |
| action | ENUM | create, update, delete, supersede, archive, restore |
| actor_type | ENUM | user, system, llm, api_client, migration |
| actor_id | TEXT | Actor identifier |
| actor_name | TEXT | Actor display name |
| reason | TEXT | Why the action was taken |
| correlation_id | TEXT | Links related events |
| timestamp | TIMESTAMPTZ | When the action occurred |
| metadata | JSONB | Action-specific details |

---

## Indexes

| Table | Index Type | Purpose |
|-------|------------|---------|
| artifacts | B-tree | tenant_id, artifact_type, source, created_at |
| artifacts | GIN | search_vector (full-text) |
| embeddings | HNSW | embedding (vector similarity) |
| relations | B-tree | source_type/id, target_type/id |
| provenance_events | B-tree | entity_type/id, timestamp |

## Constraints

- All tables have tenant_id NOT NULL with FK to tenants
- Relations prevent self-referencing (source ≠ target)
- Confidence scores constrained to 0.0-1.0 range
- Artifact version numbers are unique per artifact
