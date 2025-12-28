# Mímir Overview

*Named after the Norse keeper of the Well of Knowledge*

## What Is Mímir?

A durable, accountable memory and meta-analysis system for human thinking, centered on conversations, documents, and decisions.

Mímir serves as a **storage foundation** for preserving and querying intellectual work. It provides a clean API layer over PostgreSQL with pgvector for semantic search capabilities.

## What Mímir Is NOT

This is not:
- A chat application
- A search engine
- A productivity dashboard
- An LLM orchestrator

## Core Goals

| Goal | Description |
|------|-------------|
| **Preserve Records** | Canonical storage of conversations and writings |
| **First-Class Reasoning** | Intent, reasoning, and decisions as inspectable objects |
| **Enable Reflection** | Understand how and why conclusions were reached |
| **Reduce Cognitive Waste** | Detect redundancy, recall prior conclusions |
| **Support Evolution** | Understanding evolves without freezing ontology |
| **Balance Agency** | LLMs as assistants, not authorities |

> Turn transient conversations into a trustworthy, evolving intellectual record.

---

## Why Mímir? (vs. Standard RAG Systems)

Mímir is designed as a **storage backend for RAG systems** with multiple client applications.

### Standard RAG Comparison

| Feature | Pinecone/Weaviate/Chroma | Mímir |
|---------|--------------------------|-------|
| Vector storage | ✅ | ✅ |
| Metadata filtering | ✅ | ✅ |
| Hybrid search (RRF) | Some | ✅ |
| Managed hosting | ✅ | Self-hosted |
| Production scale | Battle-tested | Newer |

### Mímir's Unique Differentiators

| Feature | Standard RAG | Mímir |
|---------|--------------|-------|
| **Decision tracking** | ❌ | ✅ Track "why" behind choices |
| **Entity relations** | ❌ | ✅ Graph connections |
| **Spans & annotations** | ❌ | ✅ Quotes/highlights |
| **Full provenance** | ❌ | ✅ Who changed what, when, why |
| **Content versioning** | ❌ | ✅ Append-only history |
| **Multi-tenant** | App-level | ✅ Built-in |
| **External key provenance** | Basic | ✅ source_system + external_id |

### When to Use Mímir

**Choose Mímir if you need:**
- Decision tracking with reasoning chains
- Relationships between documents (knowledge graph patterns)
- Audit trails for compliance or accountability
- Meta-analysis or decision support systems
- One system for documents + decisions + provenance
- Full control via self-hosted PostgreSQL

**Choose standard RAG if you need:**
- Simple documents → embeddings → search
- Managed cloud hosting without operational overhead
- Proven scale with minimal setup

### Core Value Proposition

> Mímir isn't just a vector store — it's a **durable memory system for decisions**.

Standard RAG systems store documents. Mímir stores **knowledge with provenance**:
- What decisions were made?
- What evidence supported them?
- How have they evolved over time?
- What contradicts what?

---

## Technology Stack

| Component | Technology |
|-----------|------------|
| Database | PostgreSQL 18 + pgvector |
| API | FastAPI (Python 3.13) |
| Data Access | Raw SQL via psycopg v3 (no ORM) |
| Containerization | Docker Compose |

---

## Boundaries (Non-Goals)

Mímir is a **storage API only**. It deliberately does not:

| Not Responsible For | Why |
|---------------------|-----|
| Call LLMs | Orchestration belongs in clients |
| Generate embeddings internally | Clients choose models/providers |
| Perform chunking | Domain-specific strategy (see DD-007) |
| Make semantic judgments | No truth adjudication |
| Manage UI | Presentation is client concern |
| Orchestrate workflows | Workflow logic belongs in clients |

---

## Documentation Index

| Document | Purpose |
|----------|---------|
| [overview.md](overview.md) | This file - project vision |
| [architecture.md](architecture.md) | Core principles, entity model |
| [data-model.md](data-model.md) | Database tables and columns |
| [api-design.md](api-design.md) | REST endpoint specification |
| [search-architecture.md](search-architecture.md) | Search modes, RRF, providers |
| [design-decisions.md](design-decisions.md) | Architectural decisions (DD-001 through DD-009) |
