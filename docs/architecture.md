# Mímir V2 Architecture

## Overview

Mímir is a **durable memory system** for storing and retrieving knowledge with full provenance. It serves as a storage backend for RAG systems and decision support applications.

V2 introduces immutable artifacts with client-generated UUIDs and append-only semantics.

## Core Principles

### 1. Each Artifact Is Its Own Identity

Every artifact has a unique UUID. There is no separate "entity" or "version" concept.

**What this means:**
- Artifact A and artifact B are different, even if B "supersedes" A
- External references (bookmarks, pointers) are client responsibility
- No "current version" concept in Mímir—clients track their own references

**Rationale**: Simplicity, immutability, and philosophical purity. Identity IS the UUID.

### 2. Client-Generated UUIDv7

Clients may provide their own UUIDv7 on create. If omitted, Mímir generates one.

**Benefits:**
- Distributed creation (pre-link objects before persistence)
- Idempotency (retry with same UUID)
- Client control over identity

**UUIDv7**: Timestamp-prefixed UUIDs provide rough ordering + uniqueness.

### 3. Append-Only Content

Content tables (artifact, relation, embedding, provenance) support INSERT only.

| Operation | Status |
|-----------|--------|
| INSERT | ✅ Allowed |
| UPDATE | ❌ Not allowed |
| DELETE | ❌ Not allowed (for now) |

**Rationale**: True append-only semantics. All knowledge is permanent.

### 4. Supersedes Is Editorial Intent

The `supersedes` relation is just another relation type. It expresses that:
- The creator considers artifact B to replace artifact A
- This is a subjective assertion, not an identity equivalence
- Other clients may still reference A if they prefer it

**Rationale**: No truth adjudication. Mímir stores facts about assertions.

### 5. Positional Types via Artifacts

Spans, quotes, highlights, annotations are artifacts with:
- `parent_artifact_id` pointing to source artifact
- `start_offset` / `end_offset` for character positions
- `position_metadata` for page, line, paragraph info

**Rationale**: Single abstraction for all content reduces complexity.

### 6. Relations Are the Universal Connection Layer

All relationships between artifacts use typed relations:
- derived_from, supersedes, references
- supports, contradicts, related_to
- parent_of, child_of
- implements, resolves

**Rationale**: Arbitrary connections without schema changes.

### 7. Embeddings for Vector Search

Vector embeddings are stored separately, allowing multiple embeddings per artifact from different models.

**Rationale**: Separate update cycles; model-agnostic storage.

### 8. Provenance for Audit Trail

All creates are logged with actor (user, system, llm, api_client), action, and context.

**Rationale**: Complete audit history for compliance and accountability.

### 9. Multi-Tenant by Design

All queries are scoped by tenant_id for logical data isolation without separate databases.

**Admin tables (tenant, vocabulary)**: Support full CRUD.  
**Content tables**: Append-only.

## Entity Model

### Core Tables (V2)

| Table | Purpose | Mutability |
|-------|---------|------------|
| tenant | Multi-tenant isolation | Mutable (admin) |
| artifact_type | Type vocabulary | Mutable (admin) |
| relation_type | Relation vocabulary | Mutable (admin) |
| tenant_type | Tenant type vocabulary | Mutable (admin) |
| artifact | All content (raw + derived) | Append-only |
| relation | Connections between artifacts | Append-only |
| embedding | Vector representations | Append-only |
| provenance_event | Audit log | Append-only |

### Removed from V1

| Table | Reason |
|-------|--------|
| artifact_version | Each artifact is its own identity |
| spans | Merged into artifact (positional types) |

## Search Architecture

### Three Search Modes

| Mode | Mechanism |
|------|-----------|
| Semantic | pgvector cosine similarity via HNSW index |
| Full-text | PostgreSQL tsvector/tsquery via GIN index |
| Hybrid | Reciprocal Rank Fusion (RRF) combining both |

### Content Deduplication

`content_hash` (SHA-256) enables:
- "Have I seen this before?" queries
- Finding duplicates across the corpus
- Integrity verification

**Note**: content_hash is informational, not a unique constraint. Same content may exist in multiple artifacts (different contexts).

## Technology Stack

| Layer | Technology |
|-------|------------|
| Database | PostgreSQL 18 + pgvector |
| API | FastAPI (Python 3.14) |
| Data Access | Raw SQL via psycopg v3 |
| Migrations | Plain SQL files |
| Containerization | Docker Compose |
| UUIDs | UUIDv7 (Python 3.14 uuid.uuid7()) |

## Non-Goals

Mímir does not:
- Call LLMs or generate content
- Perform chunking (client responsibility)
- Make semantic judgments
- Manage UI or orchestrate workflows
- Track "current version" (client responsibility)
- Provide archival/lifecycle management (client responsibility)

## What Changed from V1

| Concept | V1 | V2 |
|---------|----|----|
| Primary keys | SERIAL INT | UUID (UUIDv7) |
| Versioning | artifact_version table | Each artifact is own identity |
| Identity | Entity + versions | Artifact UUID only |
| Mutations | UPDATE allowed | Append-only |
| Deletes | DELETE allowed | Not allowed (for now) |
| Supersedes | Version chain | Editorial relation |
| Current pointer | Latest version | Client tracks externally |
