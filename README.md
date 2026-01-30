# Mímir - Knowledge Graph & Semantic Memory System

A comprehensive knowledge management system with a graph-based API backend and multiple frontend interfaces.

## Repository Structure

This is a monorepo containing multiple components:

```
mimir/
├── backend/              # Mímir Knowledge Graph API
├── frontends/chatui/     # Terminal-based Chat UI
├── data/                 # Local data (gitignored)
├── docs/                 # Project-wide documentation
└── scripts/              # Utility scripts
```

## Components

### Backend - Knowledge Graph API

**Location:** `backend/`

FastAPI-based knowledge graph API with semantic search capabilities using PostgreSQL + pgvector.

**Features:**
- Unified artifact model for all knowledge types
- Multi-tenant architecture
- Semantic search with multiple embedding providers (Ollama, OpenAI)
- Graph relationships between artifacts
- Immutable provenance tracking

**Quick Start:**
```bash
cd backend
cp .env.example .env
# Edit .env to set POSTGRES_PASSWORD
docker compose up -d
docker compose exec api python -m migrations.migrate up
```

**Access:** http://localhost:38000/docs

[→ Full Backend Documentation](backend/README.md)

---

### Frontends

#### Chat UI - Terminal Interface

**Location:** `frontends/chatui/`

Terminal-based chat interface built with Textual, connecting to LLM backends with Mimir persistence.

**Components:**
- **Textual TUI**: Rich terminal chat interface
- **Chat Server**: LLM integration with Mimir persistence
- **Echo Server**: Testing server without LLM

**Quick Start:**
```bash
# Terminal 1 - Start chat server
cd frontends/chatui/servers/chat_echo_server
uvicorn src.server:app --reload --port 8001

# Terminal 2 - Start UI
cd frontends/chatui/implementations/textual
poetry run python -m src.chat_app --backend-url http://localhost:8001
```

[→ Full Chat UI Documentation](frontends/chatui/README.md)

---

## Data Directory

**Location:** `data/`

Local data storage (gitignored). Contains:
- ChatGPT exports
- Processed conversation data
- Other user-specific data

This directory is excluded from version control.

---

## Documentation

Project-wide documentation is in the `docs/` directory:

- **API & Data Model**
  - [Entity Guide](docs/entity-guide.md) - Entity relationships and usage
  - [API Design](docs/api-design.md) - API design principles
  - [Data Model](docs/data-model.md) - Database schema
  - [Search Architecture](docs/search-architecture.md) - Semantic search

- **Architecture**
  - [System Architecture](docs/architecture.md) - Overall system design

---

## Utility Scripts

**Location:** `scripts/`

Shared utility scripts for data processing and ingestion:
- `ingest_chatgpt.py` - Import ChatGPT export data into Mimir

---

## Port Reference

| Service | Port | Component |
|---------|------|-----------|
| Mimir API | 38000 | Backend |
| PostgreSQL | 35432 | Backend |
| Chat Server | 8001 | Chat UI |
| Echo Server | 8000 | Chat UI (testing) |

---

## Development Workflow

### Working on the Backend

```bash
cd backend
docker compose up -d              # Start services
docker compose logs -f api        # View logs
docker compose exec api python -m migrations.migrate status
```

### Working on Chat UI

```bash
cd frontends/chatui
# Follow component-specific setup in README.md
```

### Running Tests

```bash
cd backend
pytest                            # Run all tests
pytest -m integration             # Run integration tests only
pytest tests/unit/                # Run unit tests only
```

---

## Contributing

Each component has its own README with detailed setup and development instructions. Please refer to the component-specific documentation for contribution guidelines.

---

## License

[Your License Here]
