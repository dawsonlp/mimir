# V2 Schema Review: Original Vision Alignment

This document tracks alignment between the original project vision and our V2 implementation, plus open design questions.

## Status: ✅ Resolved (Dec 28, 2025)

---

## Original Vision (from original_conversation.txt)

Key concepts from the founding conversation:

### Core Data Model
1. **Artifact** - Universal unit for any block of data (documents, sub-documents, chunks)
2. **Analysis** - Derived content related to another artifact
3. **Intent** - First-class object capturing conversation purpose
4. **Intent Groups** - Semi-managed vocabulary for grouping related intents
5. **Decision** - Statement with rationale and status

### Storage Requirements
1. Track conversations with ingestion for outside information
2. Multiple embedding models per artifact
3. Chunks at different sizes (chapter, paragraph, sentence)
4. Hierarchical content model (parent-child relationships)
5. Positional references (quotes, highlights within content)

### Meta-Analysis Goals
1. Intent tracking: "What is this conversation trying to accomplish?"
2. Intent drift: How intent changes over time
3. Redundancy detection: "This conversation covers ground already covered"
4. Quality analysis: "What would have been a better prompt?"

---

## V2 Implementation Alignment

### ✅ Fully Implemented

| Concept | Implementation | Notes |
|---------|---------------|-------|
| Artifact as universal unit | `artifact` table with `artifact_type` enum | 17 types |
| Analysis as derived content | `artifact_type = 'analysis'` | Relates via `relation` |
| Intent as first-class | `artifact_type = 'intent'` | Content + metadata |
| Decision with rationale | `artifact_type = 'decision'` | Status in metadata |
| Multiple embedding models | `model TEXT` column | Not enum - flexible |
| Chunks as artifacts | `artifact_type = 'chunk'` | With position columns |
| Positional references | `start_offset`, `end_offset` on artifact | For quote/highlight/chunk |
| Parent-child hierarchy | `parent_artifact_id` column | Self-referential |
| Provenance tracking | `provenance_event` table | Full audit trail |

### ⚠️ Open Questions

| Concept | Current Status | Decision Needed |
|---------|---------------|-----------------|
| Intent Groups | **Missing from schema** | Add `intent_group` type? |
| Semi-managed vocabulary | No taxonomy support | How to implement? |
| Table of Contents | No explicit type | Use `summary` or add `toc`? |

---

## Open Design Question: PostgreSQL ENUMs vs Tables

### Current Approach: ENUMs

We use PostgreSQL `ENUM` types for several vocabularies:

```sql
CREATE TYPE artifact_type AS ENUM ('conversation', 'document', 'intent', ...);
CREATE TYPE relation_type AS ENUM ('references', 'supports', 'contradicts', ...);
CREATE TYPE entity_type AS ENUM ('artifact', 'artifact_version');
```

### Trade-offs

| Aspect | ENUM | Table |
|--------|------|-------|
| **Performance** | Faster (internal int) | Slightly slower (FK lookup) |
| **Validation** | Built-in | FK constraint |
| **Adding values** | `ALTER TYPE ADD VALUE` | `INSERT` |
| **Removing values** | Complex (recreate type) | `DELETE` (if not referenced) |
| **Metadata** | None | Can add description, active flag, etc. |
| **API exposure** | Need separate endpoint | Standard CRUD |
| **Migrations** | Schema change | Data change |
| **Querying by type** | Just works | `JOIN` or denormalize |

### Candidates for Each Approach

**Keep as ENUM** (stable, system-defined):
- `entity_type` - Only 2 values, unlikely to change
- `provenance_action` - Fixed system actions
- `provenance_actor_type` - Fixed actor categories

**Consider as Table** (evolving, user-extensible):
- `artifact_type` - May need new types for specific domains
- `relation_type` - Domain-specific relationships
- `tenant_type` - Could evolve with use cases

### Proposed Hybrid Approach

1. **Core system types stay as ENUMs** - stability, performance
2. **Extensible vocabularies become lookup tables** - flexibility, metadata
3. **Option C: TEXT columns with FK to vocabulary table** - maximum flexibility

#### Example: Vocabulary Table Approach

```sql
CREATE TABLE mimirdata.vocabulary (
    id SERIAL PRIMARY KEY,
    vocabulary_name TEXT NOT NULL,  -- 'artifact_type', 'relation_type'
    value TEXT NOT NULL,
    display_name TEXT,
    description TEXT,
    is_active BOOLEAN DEFAULT true,
    sort_order INT,
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE (vocabulary_name, value)
);

-- Usage: artifact_type becomes TEXT with validation
ALTER TABLE artifact ALTER COLUMN artifact_type TYPE TEXT;
ALTER TABLE artifact ADD CONSTRAINT artifact_type_valid 
    CHECK (artifact_type IN (SELECT value FROM vocabulary WHERE vocabulary_name = 'artifact_type'));
```

**Pros**: Maximum flexibility, no schema changes for new types
**Cons**: Loses enum type safety, more complex queries

---

## Missing Concept: Intent Groups

### Original Vision
> "I also think I will want to group intents; for example one might be 'The intent is to understand how sql server fits into a database strategy'"
> "Yah, effectively the intent groups are a semi-managed vocabulary"

### Options

**Option A: Add `intent_group` artifact type** (Recommended)
```sql
-- Add to artifact_type enum:
ALTER TYPE mimirdata.artifact_type ADD VALUE 'intent_group';
```
- Intent groups are artifacts with their own metadata, embeddings, provenance
- Intents relate to groups via `child_of` relation
- Consistent with "everything is an artifact"

**Option B: Metadata + Relations Only**
- Store group name in intent's `metadata.group`
- Create relations between intents manually
- No first-class group entity
- Harder to query, no group-level properties

**Option C: Separate `intent_group` Table**
- Explicit FK from intent to group
- Breaks "everything is artifact" model
- V1 approach (being migrated away from)

### Recommendation
**Option A** - add `intent_group` to `artifact_type` enum, maintaining the unified model.

---

## Action Items

- [x] **Decision**: Add `intent_group` to artifact_type? → **YES** (added)
- [x] **Decision**: Keep ENUMs or migrate to tables? → **Hybrid approach**
- [x] **Decision**: Which specific types to convert to tables?
  - **Tables**: `artifact_type`, `relation_type`, `tenant_type`
  - **ENUMs**: `entity_type`, `provenance_action`, `provenance_actor_type`
- [x] Update schema based on decisions → **Migrations rewritten**
- [ ] Update data-model.md documentation

## Implementation Summary

**Vocabulary Tables Created:**
- `artifact_type` (18 types including `intent_group`)
- `relation_type` (16 types with `inverse_code` and `is_symmetric`)
- `tenant_type` (3 types)

**System ENUMs Retained:**
- `entity_type` (artifact, artifact_version)
- `provenance_action` (create, update, delete, supersede, archive, restore)
- `provenance_actor_type` (user, system, llm, api_client, migration)

**FK Constraints:**
- `artifact.artifact_type` → `artifact_type(code)`
- `relation.relation_type` → `relation_type(code)`
- `tenant.tenant_type` → `tenant_type(code)`

---

## References

- Original conversation: `v2/docs/original_conversation.txt` (private - excluded from repo via .gitignore)
- V2 Requirements: `v2/docs/requirements.md`
- V2 Data Model: `v2/docs/data-model.md`
- Current Schema: `v2/migrations/versions/001_schema_and_tenant.up.sql`
