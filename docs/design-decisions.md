# Mímir V3 Design Decisions

## Overview

This document captures the key architectural decisions made in Mímir V3, focusing on the transition to UUIDs and append-only data patterns.

---

## Decision 1: UUIDv7 for Primary Keys

### Context
The original design used auto-incrementing integers for primary keys. This created dependencies between clients and the database—clients couldn't know IDs until after INSERT.

### Decision
Switch all content tables to UUID primary keys with UUIDv7 preferred:

- **Artifact**: UUID primary key (client-generated UUIDv7 preferred)
- **Relation**: UUID primary key, UUID references to artifacts
- **Embedding**: UUID primary key, UUID reference to artifact
- **Provenance Event**: UUID primary key, UUID entity reference

### Rationale

| Factor | Impact |
|--------|--------|
| **Distributed Creation** | Clients can generate IDs before calling API |
| **Pre-linked Graphs** | Dragonfly can build full object graphs with relationships before any persistence |
| **Idempotency** | Same UUID twice = client error (409 Conflict), not silent update |
| **No Database Dependency** | Clients don't need DB round-trip to get ID |
| **UUIDv7 Ordering** | Timestamp prefix gives creation ordering + better B-tree performance |

### Implementation Details

```sql
-- Database uses UUIDv7 primary keys by default
-- Clients can provide UUIDv7 for pre-linked graphs and idempotency
CREATE TABLE mimirdata.artifact (
    id UUID PRIMARY KEY DEFAULT uuidv7(),
    ...
);
```

```python
# API accepts optional client ID
class ArtifactCreate(BaseModel):
    id: UUID | None = None  # Client-generated UUIDv7 preferred
    artifact_type: str
    ...
```

### Duplicate Handling
- **Duplicate UUID**: 409 Conflict (client error, not create-if-not-exists)
- **Duplicate relation (source, target, type)**: 409 Conflict

---

## Decision 2: Append-Only Data Model

### Context
Traditional CRUD systems allow updates and deletes. This complicates audit trails, makes debugging harder, and creates data consistency issues in distributed systems.

### Decision
Content tables (artifact, relation, embedding) are **append-only**:
- No UPDATE operations
- No DELETE operations
- All mutations create new records

### Rationale

| Factor | Impact |
|--------|--------|
| **Complete Audit Trail** | Every state change is recorded as new entity |
| **Provenance Tracking** | Can trace any artifact back to its creation |
| **Simplified Concurrency** | No concurrent update conflicts |
| **Event Sourcing Compatible** | Can replay history, reconstruct any point in time |
| **Debug Friendly** | What you see is what was created |

### Implementation

**Removed Operations:**
- `PUT/PATCH /artifacts/{id}` - No updates
- `DELETE /artifacts/{id}` - No deletes
- `PUT/PATCH /relations/{id}` - No updates
- `DELETE /relations/{id}` - No deletes
- `DELETE /embeddings/{id}` - No deletes

**Version Pattern:**
Instead of updating an artifact, create a new artifact with a `supersedes` relation:

```
Artifact A (v1) ← supersedes ← Artifact B (v2) ← supersedes ← Artifact C (v3)
```

This preserves the entire history while clearly indicating editorial intent.

---

## Decision 3: Unified Artifact Model

### Context
The V1 design had separate tables for different content types. This created unnecessary schema complexity and JOIN overhead.

### Decision
**Everything is an artifact.** Type discrimination via `artifact_type` field.

### Artifact Categories

| Category | Types | Description |
|----------|-------|-------------|
| **Content** | conversation, document, note | Primary source material |
| **Positional** | chunk, quote, highlight, annotation, reference, bookmark | References within content |
| **Derived** | intent, decision, analysis, summary, finding, question, answer | Knowledge extracted from content |

### Hierarchy
- **parent_artifact_id**: Self-reference for tree structures (document → chunks)
- **start_offset/end_offset**: Character positions for positional types

---

## Decision 4: Vocabulary Tables for Type Safety

### Context
Using plain strings for types leads to typos and inconsistency. Using enums requires schema changes for new types.

### Decision
Use **vocabulary tables** (lookup tables with code as primary key):

- `artifact_type` - Valid artifact types
- `relation_type` - Valid relation types with inverse metadata
- `tenant_type` - Valid tenant types

### Benefits
- **Type safety**: Foreign keys enforce valid values
- **Extensibility**: Add new types with INSERT, no schema migration
- **Metadata**: Can store display names, descriptions, groupings
- **Bidirectional Relations**: `inverse_code` enables efficient graph traversal

---

## Decision 5: Simplified Provenance Model

### Context
V1 had complex provenance with multiple action types and entity type enums.

### Decision
Simplify to:
- **One action**: `create` (since we're append-only)
- **TEXT fields**: For flexibility (entity_type, actor_type)
- **Auto-creation**: Events created automatically by services, not via API

### Actor Types
- `user` - Human user
- `system` - Automated system process
- `llm` - Language model
- `api_client` - External API client
- `migration` - Database migration

---

## Decision 6: No Explicit Version Table

### Context
V1 had an `artifact_version` table to track versions separately from artifacts.

### Decision
Remove `artifact_version`. Each artifact is its own immutable identity.

### Versioning Pattern
Use the `supersedes` / `superseded_by` relation types to express editorial intent:

```python
# New version supersedes old version
POST /relations
{
    "source_id": "new-artifact-uuid",
    "target_id": "old-artifact-uuid", 
    "relation_type": "supersedes",
    "confidence": 1.0
}
```

This approach:
- Preserves both versions as first-class artifacts
- Makes version history queryable via relations
- Allows multiple "latest" versions (branching)
- Separates identity from editorial decisions

---

## Decision 7: Client-Optional UUID Generation

### Context
Forcing all clients to generate UUIDs is a burden for simple use cases.

### Decision
**Optional client ID**: If client provides UUID, use it. If not, server generates one.

```python
# Client A (Dragonfly): provides UUID for pre-linking
POST /artifacts
{"id": "01926a5c-...", "artifact_type": "situation", "content": "..."}
→ 201 Created with provided ID

# Client B (simple script): omits UUID
POST /artifacts
{"artifact_type": "document", "content": "..."}
→ 201 Created with server-generated UUID
```

---

## Migration Notes

### From V1 to V2
Since Mímir is in development with no production data:
1. Drop all existing tables
2. Run new migrations 001-005
3. Re-import any test data with new schema

### For Production Systems (Future)
If Mímir had production data, migration would require:
1. Add UUID columns to existing tables
2. Generate UUIDs for existing records
3. Update foreign keys to use UUIDs
4. Deprecate integer IDs over time

---

## API Summary

### Created Operations (V2)
| Endpoint | Action | Returns |
|----------|--------|---------|
| `POST /artifacts` | Create artifact | 201 Created / 409 Conflict |
| `GET /artifacts` | List artifacts | 200 OK |
| `GET /artifacts/{uuid}` | Get artifact | 200 OK / 404 Not Found |
| `GET /artifacts/{uuid}/children` | Get children | 200 OK |
| `POST /relations` | Create relation | 201 Created / 409 Conflict |
| `GET /relations` | List relations | 200 OK |
| `GET /relations/{uuid}` | Get relation | 200 OK / 404 Not Found |
| `GET /relations/artifact/{uuid}` | Get artifact relations | 200 OK |
| `POST /embeddings` | Create embedding | 201 Created |
| `GET /embeddings` | List embeddings | 200 OK |
| `GET /embeddings/{uuid}` | Get embedding | 200 OK / 404 Not Found |
| `GET /embeddings/artifact/{uuid}` | Get artifact embeddings | 200 OK |
| `POST /embeddings/similar` | Find similar | 200 OK |
| `GET /provenance` | List events | 200 OK |
| `GET /provenance/artifact/{uuid}` | Get artifact history | 200 OK |

### Removed Operations
- All `PUT/PATCH` endpoints (no updates)
- All `DELETE` endpoints (no deletes)
- `POST /provenance` (auto-created)
- All version-specific endpoints (artifacts are their own identity)

---

## Python Client Considerations (Dragonfly)

### UUID Generation
```python
from uuid import uuid7
artifact_id = uuid7()
```

### Pre-linking Pattern
```python
# Generate IDs before any API calls
situation_id = uuid7()
assessment_id = uuid7()
decision_id = uuid7()

# Build graph locally
situation = {"id": situation_id, "artifact_type": "situation", ...}
assessment = {"id": assessment_id, "artifact_type": "assessment", ...}
decision = {"id": decision_id, "artifact_type": "decision", ...}

# Relations reference UUIDs directly
relations = [
    {"source_id": assessment_id, "target_id": situation_id, "relation_type": "derived_from"},
    {"source_id": decision_id, "target_id": assessment_id, "relation_type": "derived_from"},
]

# Persist entire graph
for artifact in [situation, assessment, decision]:
    client.post("/artifacts", json=artifact)
for relation in relations:
    client.post("/relations", json=relation)
```

---

*Last Updated: January 2026*
