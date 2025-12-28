# Mímir

*Named after the Norse keeper of the Well of Knowledge*

A durable, accountable memory and meta-analysis system for human thinking, centered on conversations, documents, and decisions.

## Overview

Mímir serves as a **storage foundation** for preserving and querying intellectual work. It provides a clean API layer over PostgreSQL with pgvector for semantic search capabilities.

This is **not** a chat replacement, search engine, or productivity dashboard.

Instead, it aims to:

- Preserve canonical records of conversations and writings
- Make intent, reasoning, and decisions first-class, inspectable objects
- Enable reflection on how and why conclusions were reached
- Reduce cognitive waste by detecting redundancy and recalling prior conclusions
- Support evolving understanding without freezing ontology or meaning
- Balance cost, agency, and truthfulness, using LLMs as assistants—not authorities

In short:

> Turn transient conversations into a trustworthy, evolving intellectual record.

## Why Mímir? (vs. Standard RAG Systems)

Mímir is designed as a **storage backend for RAG systems** with multiple client applications. But why not use Pinecone, Weaviate, Chroma, or plain pgvector?

### Standard RAG Systems

| Feature | Pinecone/Weaviate/Chroma | Mímir |
|---------|--------------------------|-------|
| Vector storage | ✅ | ✅ |
| Metadata filtering | ✅ | ✅ |
| Hybrid search | Some | ✅ RRF fusion |
| Managed hosting | ✅ | Self-hosted |
| Production scale | ✅ Battle-tested | Newer |

### Mímir's Unique Differentiators

| Feature | Standard RAG | Mímir |
|---------|--------------|-------|
| **Intent & Decision tracking** | ❌ | ✅ Track "why" behind choices |
| **Entity relations** | ❌ | ✅ Graph connections between entities |
| **Spans & annotations** | ❌ | ✅ Quotes/highlights within documents |
| **Full provenance/audit** | ❌ | ✅ Who changed what, when, why |
| **Content versioning** | ❌ | ✅ Append-only artifact history |
| **Multi-tenant isolation** | App-level | ✅ Built-in tenant_id |
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

See [design_decisions.md](design_decisions.md) for architectural decisions including DD-007 (Chunking Strategy) and DD-008 (Search Filters).

## Architecture

Mímir is a **storage API only**. It deliberately does not:
- Call LLMs or embedding endpoints
- Perform orchestration or workflow execution
- Make semantic judgments or truth adjudication
- Manage UI or presentation concerns

See [requirements.md](requirements.md) for the complete requirements and non-goals.

### Technology Stack

| Component | Technology |
|-----------|------------|
| **Database** | PostgreSQL 18 + pgvector |
| **API** | FastAPI (Python 3.13) |
| **Data Access** | Raw SQL via psycopg v3 (no ORM) |
| **Containerization** | Docker Compose |

See [infrastructure_and_tools_development_plan.txt](infrastructure_and_tools_development_plan.txt) for detailed technical design.

## Documentation

| Document | Description |
|----------|-------------|
| [readme.md](readme.md) | This file - project overview |
| [requirements.md](requirements.md) | V1-V3 requirements, non-goals, and boundaries |
| [infrastructure_and_tools_development_plan.txt](infrastructure_and_tools_development_plan.txt) | Technical implementation plan |
| [project_tracking.md](project_tracking.md) | Issue tracking and conventions |

## Quick Start

*Coming soon - implementation in progress*

```bash
# Clone the repository
git clone <your-repo-url>
cd mimir

# Copy environment template and configure
cp .env.example .env
# Edit .env with your values (POSTGRES_PASSWORD, DOCKER_BUILDX_BUILDER, etc.)

# Start services
docker compose up -d

# API available at http://localhost:38000
# Swagger docs at http://localhost:38000/docs
```

## Project Status

**Phase:** V1 Complete ✅

| Phase | Status |
|-------|--------|
| Phase 1: Foundation | ✅ Complete |
| Phase 2: Core Entities | ✅ Complete |
| Phase 3: Intent & Decisions | ✅ Complete |
| Phase 4: Spans & Relations | ✅ Complete |
| Phase 5: Search & Embeddings | ✅ Complete |
| Phase 6: Provenance & Polish | ✅ Complete |
| Phase 7: Advanced RAG Features | 🚧 Planned |

### Current Capabilities
- **Artifacts**: Documents, conversations, notes with versioning
- **Intents & Decisions**: Track reasoning and choices
- **Spans & Relations**: Annotations and entity connections
- **Search**: Semantic (pgvector), full-text (tsvector), hybrid (RRF)
- **Embeddings**: Voyage AI, OpenAI, Ollama providers
- **Provenance**: Full audit trail with actor/action tracking
- **Multi-tenant**: Built-in tenant isolation

See [project_tracking.md](project_tracking.md) for detailed progress.

## License

*TBD*

## Contributing

*TBD*
