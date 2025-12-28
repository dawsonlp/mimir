# Mímir V2 Architecture

## Overview

Mímir is a **durable memory system** for storing and retrieving knowledge with full provenance. It serves as a storage backend for RAG systems and decision support applications.

V2 consolidates all knowledge types into a unified artifact model.

## Core Principles

### 1. Everything Is an Artifact

All content—raw and derived—is stored as artifacts with type discrimination.

**Raw Content Types**: conversation, document, note, chunk

**Derived Knowledge Types**: intent, decision, analysis, summary, conclusion, finding, question, answer

**Rationale**: Single abstraction reduces complexity, enables unified search, and provides flexibility for unknown future use cases.

### 2. Relations Are the Universal Connection Layer

All relationships between entities use polymorphic relations with typed connections:
- resolves, derived_from, child_of, supersedes
- supports, contradicts, references, related_to
- parent_of, implements

**Rationale**: Arbitrary connections without schema changes.

### 3. Spans for Positional Annotations

Spans mark specific positions within artifact content: quotes, highlights, annotations, references, bookmarks.

**Rationale**: Positional references are fundamentally different from content and warrant their own table.

### 4. Embeddings for Vector Search

Vector embeddings are stored separately, allowing multiple embeddings per artifact from different models.

**Rationale**: Separate update cycles; model-agnostic storage.

### 5. Provenance for Audit Trail

All changes are logged with actor (user, system, llm), action (create, update, delete, supersede), and context.

**Rationale**: Complete audit history for compliance and accountability.

### 6. Multi-Tenant by Design

All queries are scoped by tenant_id for logical data isolation without separate databases.

## Entity Model

### Core Tables (V2)

| Table | Purpose |
|-------|---------|
| tenants | Multi-tenant isolation |
| artifacts | All content (raw + derived) |
| artifact_versions | Append-only content history |
| relations | Polymorphic connections |
| spans | Positional annotations |
| embeddings | Vector representations |
| provenance_events | Audit log |

### Simplified from V1

**Removed Tables**: intents, intent_groups, decisions

These become artifact types linked via relations.

## Search Architecture

### Three Search Modes

| Mode | Mechanism |
|------|-----------|
| Semantic | pgvector cosine similarity via HNSW index |
| Full-text | PostgreSQL tsvector/tsquery via GIN index |
| Hybrid | Reciprocal Rank Fusion (RRF) combining both |

### Embedding Providers

Pluggable architecture supporting Voyage AI, OpenAI, and Ollama.

## Technology Stack

| Layer | Technology |
|-------|------------|
| Database | PostgreSQL 18 + pgvector |
| API | FastAPI (Python 3.13) |
| Data Access | Raw SQL via psycopg v3 |
| Migrations | Plain SQL files |
| Containerization | Docker Compose |

## Non-Goals

Mímir does not:
- Call LLMs or generate content
- Perform chunking (client responsibility)
- Make semantic judgments
- Manage UI or orchestrate workflows
