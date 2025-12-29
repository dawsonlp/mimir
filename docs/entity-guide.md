# Mímir V2 Entity Guide

This guide explains each entity in the Mímir data model, their relationships, and effective usage patterns.

---

## Entity Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         TENANT                                   │
│  (Isolated namespace for all data - multi-tenancy boundary)     │
└─────────────────────────────────────────────────────────────────┘
                                │
                                │ owns
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                        ARTIFACT                                  │
│  (Universal knowledge unit - everything is an artifact)         │
│                                                                  │
│  Types: conversation, document, note, chunk, quote,             │
│         intent, decision, analysis, summary, finding...         │
└─────────────────────────────────────────────────────────────────┘
         │              │                      │
         │              │                      │
    versions        connected to           searchable via
         │              │                      │
         ▼              ▼                      ▼
┌─────────────┐  ┌─────────────┐      ┌─────────────┐
│  ARTIFACT   │  │  RELATION   │      │  EMBEDDING  │
│  VERSION    │  │             │      │             │
│             │  │ references  │      │ vector(N)   │
│ (immutable  │  │ supports    │      │ semantic    │
│  snapshots) │  │ derived_from│      │ search      │
└─────────────┘  │ parent_of   │      └─────────────┘
                 │ resolves    │
                 └─────────────┘
                        │
                        │
              audit trail for all
                        │
                        ▼
              ┌─────────────┐
              │ PROVENANCE  │
              │   EVENT     │
              │             │
              │ who, what,  │
              │ when, why   │
              └─────────────┘
```

---

## 1. Tenant

**Purpose:** Provides complete data isolation for multi-tenant deployments.

**Key Points:**
- Every other entity belongs to exactly one tenant
- All API calls require `X-Tenant-ID` header
- Tenants cannot see each other's data

**Usage:**
```bash
# Create tenant
POST /api/v1/tenants
{ "name": "Acme Corp", "tenant_type": "organization" }

# All subsequent calls
curl -H "X-Tenant-ID: 1" ...
```

**Tenant Types:** `user`, `organization`, `system`

---

## 2. Artifact

**Purpose:** The universal knowledge unit. All knowledge—documents, conversations, intents, decisions, chunks—is stored as artifacts.

**Key Points:**
- Type determined by `artifact_type` (extensible vocabulary table)
- Can have parent artifacts (for hierarchical structures like chunks)
- Can have positional data (start_offset, end_offset for sub-document references)
- Full-text searchable via `search_vector`
- Metadata stored as JSONB for flexibility

**Categories:**

| Category | Types | Description |
|----------|-------|-------------|
| **Content** | conversation, document, note | Primary source material |
| **Positional** | chunk, quote, highlight, annotation | References within source content |
| **Derived** | intent, decision, analysis, summary, finding, question, answer | Knowledge extracted/synthesized from sources |

**Usage:**
```bash
# Create a document artifact
POST /api/v1/artifacts
{
  "artifact_type": "document",
  "title": "Architecture Proposal",
  "content": "We propose using PostgreSQL with pgvector...",
  "source": "user"
}

# Create a chunk (positional artifact)
POST /api/v1/artifacts
{
  "artifact_type": "chunk",
  "parent_artifact_id": 1,
  "content": "PostgreSQL with pgvector",
  "start_offset": 20,
  "end_offset": 44
}

# Create a decision (derived artifact)
POST /api/v1/artifacts
{
  "artifact_type": "decision",
  "title": "Use PostgreSQL",
  "content": "After analysis, we chose PostgreSQL 18...",
  "metadata": { "status": "active", "confidence": 0.95 }
}
```

**Hierarchy:** Use `parent_artifact_id` to create trees:
- Document → Chunks
- Intent Group → Intents
- Conversation → Derived Summaries

---

## 3. Artifact Version

**Purpose:** Immutable snapshot of an artifact at a point in time. Enables change tracking and rollback.

**Key Points:**
- Automatically created on artifact update
- Append-only (never modified or deleted)
- Contains full content snapshot
- Links back to source artifact via `artifact_id`

**Usage:**
```bash
# Get all versions of an artifact
GET /api/v1/artifacts/123/versions

# Get specific version
GET /api/v1/artifacts/123/versions/2
```

**When Versions Are Created:**
- On every `PUT /api/v1/artifacts/{id}` call
- Before any content modification
- Stores: version_number, full content, change metadata

---

## 4. Relation

**Purpose:** Connects any two entities (artifacts or artifact versions). Forms the knowledge graph.

**Key Points:**
- Source and target can be artifacts or artifact_versions
- Relation type from vocabulary table (extensible)
- Bidirectional queries supported (outgoing + incoming)
- Unique constraint prevents duplicate relations

**Relation Types:**

| Type | Inverse | Use Case |
|------|---------|----------|
| `references` | `referenced_by` | Citations, links |
| `supports` | `supported_by` | Evidence backing claims |
| `contradicts` | (symmetric) | Conflicting information |
| `derived_from` | `source_of` | Lineage tracking |
| `supersedes` | `superseded_by` | Versioning of concepts |
| `parent_of` | `child_of` | Hierarchical grouping |
| `implements` | `implemented_by` | Requirements → solutions |
| `resolves` | `resolved_by` | Questions → answers, intents → decisions |
| `related_to` | (symmetric) | General association |

**Usage:**
```bash
# Link a decision to its source intent
POST /api/v1/relations
{
  "source_type": "artifact",
  "source_id": 101,
  "target_type": "artifact",
  "target_id": 50,
  "relation_type": "resolves"
}

# Query all relations for an artifact
GET /api/v1/relations/artifact/101

# Query only incoming relations
GET /api/v1/relations/artifact/101/incoming
```

**Common Patterns:**
- Decision `resolves` Intent
- Summary `derived_from` Document
- Chunk `child_of` Document
- Analysis `supports` Decision

---

## 5. Embedding

**Purpose:** Vector representation for semantic search. Enables "find similar" queries.

**Key Points:**
- One embedding per (entity, model, chunk_index) combination
- Vector dimensions vary by model (768 to 3072)
- HNSW index for fast approximate nearest neighbor
- Chunk index supports multi-vector documents

**Supported Models:**
- OpenAI: `text-embedding-3-small` (1536d), `text-embedding-3-large` (3072d)
- Ollama: `nomic-embed-text` (768d), `mxbai-embed-large` (1024d)

**Usage:**
```bash
# Create embedding for an artifact
POST /api/v1/embeddings
{
  "entity_type": "artifact",
  "entity_id": 123,
  "model": "text-embedding-3-small"
}

# Find similar artifacts
POST /api/v1/embeddings/similar
{
  "text": "database architecture decisions",
  "model": "text-embedding-3-small",
  "limit": 10
}

# Semantic search
POST /api/v1/search/semantic
{
  "query": "PostgreSQL performance optimization",
  "model": "text-embedding-3-small",
  "limit": 20
}
```

**Chunking:** For long documents, create multiple embeddings:
```bash
POST /api/v1/embeddings
{
  "entity_type": "artifact",
  "entity_id": 123,
  "chunk_index": 0,
  "chunk_text": "First 500 words..."
}
```

---

## 6. Provenance Event

**Purpose:** Immutable audit trail. Records who did what, when, and why.

**Key Points:**
- Append-only (never modified or deleted)
- Records every significant action
- Enables compliance and debugging
- Supports querying by entity, actor, time range

**Action Types:**
- `create` - Entity created
- `update` - Entity modified
- `delete` - Entity removed
- `supersede` - Entity replaced by newer version
- `archive` - Entity made inactive
- `restore` - Entity reactivated

**Actor Types:**
- `user` - Human via UI
- `system` - Internal process
- `llm` - AI/LLM operation
- `api_client` - External API consumer
- `migration` - Data migration

**Usage:**
```bash
# Query history of an artifact
GET /api/v1/provenance/entity/artifact/123

# Query all activity by a user
GET /api/v1/provenance/actor/user/john@example.com

# Record custom provenance
POST /api/v1/provenance
{
  "entity_type": "artifact",
  "entity_id": 123,
  "action": "update",
  "actor_type": "user",
  "actor_id": "jane@example.com",
  "details": { "reason": "Fixed typo in title" }
}
```

---

## Entity Relationships Summary

```
Tenant ──owns──▶ Artifact ──has──▶ ArtifactVersion
                    │
                    ├──parent_of──▶ Artifact (child)
                    │
                    ├──connected via──▶ Relation ◀──connected to── Artifact
                    │
                    ├──searchable via──▶ Embedding
                    │
                    └──tracked by──▶ ProvenanceEvent
```

---

## Common Workflows

### 1. Ingest a Document with Chunks

```bash
# 1. Create document artifact
POST /api/v1/artifacts
{ "artifact_type": "document", "title": "Report", "content": "..." }
# Returns: { "id": 1 }

# 2. Create chunk artifacts
POST /api/v1/artifacts
{ "artifact_type": "chunk", "parent_artifact_id": 1, 
  "content": "First section...", "start_offset": 0, "end_offset": 500 }

# 3. Embed the chunks
POST /api/v1/embeddings
{ "entity_type": "artifact", "entity_id": 2, "model": "text-embedding-3-small" }
```

### 2. Record a Decision from Intent

```bash
# 1. Create intent artifact
POST /api/v1/artifacts
{ "artifact_type": "intent", "title": "Choose database", "content": "..." }
# Returns: { "id": 10 }

# 2. Create decision artifact
POST /api/v1/artifacts
{ "artifact_type": "decision", "title": "Use PostgreSQL", "content": "..." }
# Returns: { "id": 11 }

# 3. Link decision to intent
POST /api/v1/relations
{ "source_type": "artifact", "source_id": 11,
  "target_type": "artifact", "target_id": 10,
  "relation_type": "resolves" }

# 4. Link decision to source conversation
POST /api/v1/relations
{ "source_type": "artifact", "source_id": 11,
  "target_type": "artifact", "target_id": 5,
  "relation_type": "derived_from" }
```

### 3. Semantic Search with Graph Traversal

```bash
# 1. Semantic search for relevant artifacts
POST /api/v1/search/semantic
{ "query": "database performance", "limit": 5 }
# Returns: artifacts 10, 11, 15

# 2. Get relations for top result
GET /api/v1/relations/artifact/10
# Returns: related intents, decisions, sources

# 3. Build knowledge context from graph
```

---

## Best Practices

1. **Use specific artifact types** - Prefer `decision` over `note` for decisions
2. **Link everything** - Relations are cheap; knowledge graphs are valuable
3. **Embed for search** - No embedding = invisible to semantic search
4. **Use parent_artifact_id** - For chunks, quotes, and hierarchies
5. **Record provenance** - Automatic for CRUD, manual for business events
6. **Query by type** - `GET /api/v1/artifacts?artifact_type=decision`

---

## Quick Reference

| Entity | Primary Key | Tenant-Scoped | Mutable | Purpose |
|--------|-------------|---------------|---------|---------|
| Tenant | id | No | Yes | Multi-tenancy isolation |
| Artifact | id | Yes | Yes | Universal knowledge unit |
| ArtifactVersion | id | Yes | No | Change history |
| Relation | id | Yes | Yes | Knowledge graph edges |
| Embedding | id | Yes | Yes | Semantic search vectors |
| ProvenanceEvent | id | Yes | No | Audit trail |
