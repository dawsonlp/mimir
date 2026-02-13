# Mímir Naming Conventions

This document defines the naming conventions used across database, API, and schema layers.

---

## Core Naming Convention

All layers (database columns, API parameters, Pydantic fields) use **identical names**. No translation occurs between layers.

### Case Convention

| Layer | Convention | Example |
|-------|------------|---------|
| Database columns | `snake_case` | `artifact_type`, `created_at` |
| API parameters | `snake_case` | `artifact_type`, `created_at` |
| JSON fields | `snake_case` | `artifact_type`, `created_at` |
| Schema fields | `snake_case` | `artifact_type`, `created_at` |

---

## Field Categories

### 1. Identifiers (IDs)

| Pattern | Usage | Examples |
|---------|-------|----------|
| `id` | Primary key (on the entity itself) | `tenant.id`, `artifact.id` |
| `{entity}_id` | Foreign key reference to another entity | `tenant_id`, `artifact_id`, `source_id`, `target_id`, `embedding_id`, `entity_id` |

**Rule:** Use `id` alone only for the current entity's PK. Use `{entity}_id` for all FK references.

---

### 2. Short Codes

| Pattern | Usage | Examples |
|---------|-------|----------|
| `code` | Vocabulary table primary key (text) | `artifact_type.code`, `relation_type.code`, `embedding_type.code` |
| `shortname` | User-facing unique identifier | `tenant.shortname` |

**Rule:** `code` is for internal vocab lookups. `shortname` is for user-visible identifiers.

---

### 3. Names & Labels

| Pattern | Usage | Examples |
|---------|-------|----------|
| `name` | Entity name (non-vocabulary) | `tenant.name` |
| `display_name` | Human-readable label (vocabulary tables) | `artifact_type.display_name`, `relation_type.display_name` |
| `title` | Content title (artifacts) | `artifact.title` |

**Rule:** 
- `name` = entity's name field
- `display_name` = vocab table's human label
- `title` = content/artifact title

---

### 4. Description

| Pattern | Usage | Examples |
|---------|-------|----------|
| `description` | Long-form description text | All vocab tables + `tenant.description` |

**Rule:** Always `description` (not `desc`, `summary`, etc.)

---

### 5. Type Discriminators

| Pattern | Usage | Examples |
|---------|-------|----------|
| `{entity}_type` | Type code (FK to vocab or discriminator) | `artifact_type`, `relation_type`, `embedding_type`, `tenant_type`, `entity_type`, `actor_type` |

**Rule:** Always `{entity}_type` pattern, not `type` alone.

---

### 6. Boolean Flags

| Pattern | Usage | Examples |
|---------|-------|----------|
| `is_{adjective}` | State flags | `is_active`, `is_symmetric` |
| `{verb}_{noun}` | Action toggles (query params) | `include_content`, `include_vector`, `active_only` |

**Rule:** DB columns use `is_` prefix. Query params may use action verbs.

---

### 7. Standard Fields

| Field | Type | Usage | Present On |
|-------|------|-------|------------|
| `created_at` | `TIMESTAMPTZ` | Creation timestamp | All tables |
| `metadata` | `JSONB` | Extension properties | All content tables |
| `sort_order` | `INT` | Display ordering | Vocab tables |

**Rule:** No `updated_at` field - system is append-only.

---

### 8. Pagination

| Field | Type | Default | Usage |
|-------|------|---------|-------|
| `limit` | `int` | 50 | Max results per page |
| `offset` | `int` | 0 | Skip count |
| `total` | `int` | N/A | Total count in response |

---

### 9. Response Containers

| Field | Usage |
|-------|-------|
| `items` | List of results in ListResponse |
| `results` | List of results in SearchResponse |

---

## API Schema Naming

| Pattern | Usage | Example |
|---------|-------|---------|
| `{Entity}Create` | POST request body | `ArtifactCreate`, `EmbeddingCreate` |
| `{Entity}Update` | PATCH request body | `TenantUpdate`, `ArtifactTypeUpdate` |
| `{Entity}Response` | Single item response | `ArtifactResponse`, `TenantResponse` |
| `{Entity}ListResponse` | Paginated list response | `ArtifactListResponse`, `RelationListResponse` |
| `{Action}Request` | Action-specific request | `SimilaritySearchRequest`, `SemanticSearchRequest` |
| `{Action}Response` | Action-specific response | `SimilaritySearchResponse`, `SearchResponse` |

---

## Audit Result (2025-01-31)

All database columns, API parameters, and schema fields were audited and found to be **100% consistent**.

| Table | Columns Audited | Match Status |
|-------|-----------------|--------------|
| tenant | 8 | ✅ All match |
| artifact | 15 | ✅ All match |
| relation | 8 | ✅ All match |
| embedding | 6 | ✅ All match |
| embedding_type | 11 | ✅ All match |
| provenance_event | 10 | ✅ All match |

---

## Issues Found (Structural, Not Naming)

The following structural issues have been **resolved**.

### ✅ Resolved (2025-01-31)

- [x] `POST /search/semantic` - Now uses `SemanticSearchRequest` schema with `query_vector` field
- [x] `POST /search/hybrid` - Now uses `HybridSearchRequest` schema with `query_vector` field
- [x] Consistent with `POST /embeddings/similar` which uses `SimilaritySearchRequest.query_vector`

### Implementation

Created proper request schemas that wrap the vector:

**SemanticSearchRequest:**
```python
class SemanticSearchRequest(BaseModel):
    query_vector: list[float]         # Vector wrapped in named field
    embedding_type: str               # Required
    artifact_types: list[str] | None  # Optional filter
    limit: int = 20                   # Pagination
    similarity_threshold: float = 0.0 # Score filter
    related_to: UUID | None           # Graph filter
    relation_type: str | None         # Relation type filter
    relation_direction: RelationDirection = "both"
```

**HybridSearchRequest:**
```python
class HybridSearchRequest(BaseModel):
    query: str                        # Text for fulltext matching
    query_vector: list[float]         # Vector for semantic matching
    embedding_type: str               # Required
    artifact_types: list[str] | None  # Optional filter
    limit: int = 20                   # Pagination
    rrf_k: int = 60                   # RRF constant
    semantic_weight: float = 0.5      # Balance (0=fulltext, 1=semantic)
    related_to: UUID | None           # Graph filter
    relation_type: str | None         # Relation type filter
    relation_direction: RelationDirection = "both"
```

All vector search endpoints now have consistent request body structure.

---

## Compliance Checklist

Before each PR, verify:

- [ ] New IDs use `{entity}_id` pattern for FKs
- [ ] New types use `{entity}_type` pattern
- [ ] New booleans use `is_` prefix (or action verb for query params)
- [ ] New vocab tables have `code`, `display_name`, `description`, `is_active`, `sort_order`, `created_at`
- [ ] New content tables have `id`, `tenant_id`, `created_at`, `metadata`
- [ ] No `updated_at` fields (append-only design)
- [ ] List endpoints return `{items, total, limit, offset}`
- [ ] Search endpoints return `{results, total, query}`
- [ ] All POST bodies use named request schemas