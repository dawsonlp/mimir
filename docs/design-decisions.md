# Mímir V2 Design Decisions

This document records architectural decisions. Design decisions are numbered sequentially.

---

## DD-001: Dedicated PostgreSQL Schema

Use a dedicated PostgreSQL schema named `mimirdata` for all Mímir tables.

**Rationale:**
- Keeps Mímir data isolated from other applications
- Clean separation from `public` schema (allows coexistence with LangGraph, etc.)
- Supports future schema versioning

---

## DD-002: Multi-Tenant Architecture

All entity tables reference `tenant_id` for logical data partitioning.

**Tenant Model:**
| Column | Purpose |
|--------|---------|
| id | Primary key |
| shortname | Unique identifier (e.g., "production", "research") |
| tenant_type | environment, project, experiment |
| is_active | Soft delete flag |

**API:** Tenant specified via `X-Tenant-ID` header. All queries automatically filtered.

**Rationale:**
- Complete data isolation without separate databases
- Easy to query/export by project context
- Supports multiple concurrent experiments

---

## DD-003: Raw SQL (No ORM, No Alembic)

Use raw SQL via psycopg v3 for all data access AND schema definitions.

**Migration Format:** Plain SQL files with a simple Python runner
- `001_create_tenants.up.sql` / `.down.sql`
- Commands: `migrate up`, `migrate down`, `migrate status`

**Rationale:**
- PostgreSQL features (pgvector, FTS, recursive CTEs, JSONB) require raw SQL
- Schema is stable, not rapidly evolving
- SQL is transparent about database operations
- Rollback support via `.down.sql` files

---

## DD-004: Flexible Dependency Versions During Development

Do NOT lock specific versions during active development.

**Rationale:**
- Receive fixes, security patches, and advances
- Rapidly-evolving libraries (FastAPI, Pydantic, psycopg) improve frequently
- Lock versions only when moving to QA/Production

---

## DD-005: SERIAL Primary Keys (Not UUID)

Use PostgreSQL SERIAL (auto-increment integers) for all primary keys.

**Rationale:**
| Factor | SERIAL | UUID |
|--------|--------|------|
| Storage | 4 bytes | 16 bytes |
| Index performance | Faster B-tree | Slower |
| Simplicity | Server-generated | Complexity |

**External References:** Use `external_id` column to store original source IDs (ChatGPT conversation ID, Confluence page ID, etc.)

**API:** IDs are server-assigned only; clients never provide IDs on creation.

---

## DD-006: Pluggable Embedding Provider Architecture

Support multiple embedding providers with auto-detection and fallback.

**Supported Providers:**
| Provider | Priority | Environment Variable |
|----------|----------|---------------------|
| Voyage AI | Primary (Anthropic recommended) | VOYAGE_API_KEY |
| OpenAI | Fallback | OPENAI_API_KEY |
| Ollama | Local/offline | OLLAMA_BASE_URL |

**Provider Interface:**
- `list_models()` - Dynamic model discovery
- `generate_embedding()` - Single text
- `generate_embeddings_batch()` - Multiple texts
- `is_configured()` - Check API key availability

**Model IDs:** String-based (not enums) for flexibility with new models.

---

## DD-007: Client-Side Chunking Strategy

Chunking is the responsibility of import clients, not the storage layer.

**Rationale:**
- Different content types need different strategies (code, markdown, conversations)
- Domain expertise belongs in client applications
- Storage layer stays ontology-agnostic

**Pattern:**
1. Client imports parent document (artifact_type: document)
2. Client creates chunk artifacts (artifact_type: chunk)
3. Client creates child_of relations between chunks and parent
4. Client creates embeddings for chunks

---

## DD-008: Advanced Search Filters

Search API supports filtering beyond artifact_types.

**Supported Filters:**
- artifact_types, source, source_system
- created_after, created_before
- metadata_filters (JSONB containment)
- parent_artifact_id (search within document's chunks)

---

## DD-009: Unified Artifact Model (V2)

**Date:** December 28, 2025  
**Status:** Accepted

Consolidate Intent and Decision tables into the Artifact abstraction.

**V1 Tables:**
- artifacts, intents, intent_groups, decisions (separate tables)

**V2 Tables:**
- artifacts (with extended type enum including intent, decision, analysis, etc.)

**Artifact Types:**
- Raw: conversation, document, note, chunk
- Derived: intent, decision, analysis, summary, conclusion, finding, question, answer

**Entity Types (simplified):**
- artifact, artifact_version, span

**Rationale:**
- Single abstraction reduces complexity
- Enables unified search across all knowledge types
- Provides flexibility for unknown future use cases
- Reduces table proliferation (each concept ≠ new table + service + router)
- Avoids ontological commitment before domain is understood

**Patterns for Derived Knowledge:**
- Decision → Intent: Use relation with type "resolves"
- Decision → Source: Use relation with type "derived_from"
- Supersession: Use relation with type "supersedes"

---

## Index

| ID | Title | Date |
|----|-------|------|
| DD-001 | Dedicated PostgreSQL Schema | Dec 26, 2025 |
| DD-002 | Multi-Tenant Architecture | Dec 26, 2025 |
| DD-003 | Raw SQL (No ORM) | Dec 26, 2025 |
| DD-004 | Flexible Dependency Versions | Dec 26, 2025 |
| DD-005 | SERIAL Primary Keys | Dec 26, 2025 |
| DD-006 | Pluggable Embedding Providers | Dec 28, 2025 |
| DD-007 | Client-Side Chunking | Dec 28, 2025 |
| DD-008 | Advanced Search Filters | Dec 28, 2025 |
| DD-009 | Unified Artifact Model | Dec 28, 2025 |
