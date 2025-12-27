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

**Phase:** Initial Implementation (V1 Foundation)

Current focus:
- [ ] Project scaffolding
- [ ] Docker Compose infrastructure
- [ ] Core entity models (Artifacts, Intents, Decisions, Spans, Relations)
- [ ] Basic CRUD API endpoints
- [ ] Search capabilities (FTS + vector)

## License

*TBD*

## Contributing

*TBD*
