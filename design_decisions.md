# Mímir Design Decisions

This document records architectural and design decisions for the Mímir storage system.

## DD-001: Dedicated PostgreSQL Schema (mimirdata)

**Date:** December 26, 2025  
**Status:** Accepted  

### Context
We need to organize database tables in a way that:
- Keeps Mímir data isolated from other applications
- Allows clean separation from any coexisting tables (e.g., LangGraph)
- Supports future schema versioning

### Decision
Use a dedicated PostgreSQL schema named `mimirdata` for all Mímir tables.

### Implementation
```sql
-- In init-scripts/01-create-extensions.sql
CREATE SCHEMA IF NOT EXISTS mimirdata;
ALTER DATABASE mimir SET search_path TO mimirdata, public;
CREATE EXTENSION IF NOT EXISTS vector SCHEMA mimirdata;
```

### Consequences
- All table references use the `mimirdata` schema
- Extensions (pgvector) are installed within the schema
- Clean separation from `public` schema
- SQL migrations target the `mimirdata` schema

---

## DD-002: Multi-Tenant Architecture

**Date:** December 26, 2025  
**Status:** Accepted  

### Context
We need to segment data by different contexts:
- **Deployment environments**: development, qa, production
- **Project contexts**: systems_architecture, book_writing, research, etc.

This is not multi-user authentication, but logical data partitioning within a single database.

### Decision
Introduce a `tenants` table that all entity tables reference via `tenant_id`.

### Tenant Model
```
mimirdata.tenants
├── id (serial, PK)
├── shortname (text, unique) -- e.g., "development", "systems_architecture"
├── name (text) -- Display name
├── tenant_type (enum: environment, project, experiment)
├── description (text, nullable)
├── is_active (boolean, default true)
├── created_at (timestamptz)
└── metadata (jsonb) -- extensible properties
```

### Entity Table Changes
All entity tables gain a `tenant_id` column:
```
artifacts
├── id (serial, PK)
├── tenant_id (int, FK → tenants.id, NOT NULL)
├── artifact_type (enum)
├── ...
```

### API Implications
- Tenant specified via header: `X-Tenant-ID: <int>` or `X-Tenant-Shortname: <shortname>`
- All queries automatically filtered by tenant
- Tenant context resolved at middleware level
- Default tenant configurable per environment

### Example Tenants
| shortname | name | tenant_type |
|------|------|-------------|
| development | Development | environment |
| qa | QA | environment |
| production | Production | environment |
| systems_architecture | Systems Architecture | project |
| book_writing | Book Writing | project |
| llm_research | LLM Research | experiment |

### Consequences
- Complete data isolation between tenants
- Easy to query/export data by project context
- Supports multiple concurrent experiments
- No need for separate databases per context
- Index strategy must include tenant_id for performance

---

## DD-003: SQL as Implementation Language (No ORM, No Alembic)

**Date:** December 26, 2025  
**Status:** Accepted  
**Updated:** December 26, 2025  

### Context
We considered using SQLAlchemy ORM vs. raw SQL for data access. Initially used SQLAlchemy Core with Alembic for migrations, but this introduced unnecessary abstraction.

### Decision
Use raw SQL via psycopg v3 for all data access AND schema definitions. No ORM, no SQLAlchemy at all.

### Migration Approach
Plain SQL migration files with a simple runner:
```
migrations/
├── versions/
│   ├── 001_create_tenants.up.sql
│   ├── 001_create_tenants.down.sql
│   └── ...
├── migrate.py          # Minimal migration runner
└── README.md
```

Commands:
```bash
poetry run python -m migrations.migrate up      # Apply pending
poetry run python -m migrations.migrate down    # Rollback last
poetry run python -m migrations.migrate status  # Show status
```

### Rationale
- API is request→SQL→response, not object-graph-centric
- PostgreSQL features (pgvector, FTS, recursive CTEs, JSONB) require raw SQL
- Schema is stable and deliberate, not rapidly evolving
- SQL is transparent about what the database actually does
- **Schema definitions should also be SQL, not Python abstractions**
- Rollback support via `.down.sql` files

### Consequences
- Queries written in `.sql` files or as SQL strings
- Schema changes are pure SQL migrations
- No lazy loading or relationship traversal magic
- Full control over query optimization
- Migrations tracked in `mimirdata.schema_migrations` table

---

## DD-005: SERIAL Primary Keys (Not UUID)

**Date:** December 26, 2025  
**Status:** Accepted  

### Context
Choosing between UUID and SERIAL (auto-increment) for primary keys.

### Decision
Use SERIAL (PostgreSQL auto-increment integers) for all primary keys. Use INT for foreign keys.

### Rationale
- **Storage efficiency**: INT = 4 bytes vs UUID = 16 bytes per row per FK
- **Index performance**: Smaller keys = faster B-tree operations
- **Simplicity**: Server-generated, opaque identifiers
- **Single database**: No distributed system collision concerns
- **External references**: `external_id` column stores original source IDs (e.g., ChatGPT conversation ID)
- **YAGNI**: If we ever need global uniqueness, we can add migration columns then

### API Implications
- IDs are server-assigned only; clients never provide IDs on creation
- API returns integer IDs: `{"id": 42, ...}`
- Clients use returned IDs for subsequent operations

### Consequences
- Smaller tables and indexes
- Faster joins and lookups
- IDs are sequential (not globally unique, but that's fine for single-database)
- External traceability via `external_id` metadata column

---

## DD-004: Flexible Dependency Versions During Development

**Date:** December 26, 2025  
**Status:** Accepted  

### Context
Should we lock dependency versions during development?

### Decision
Do NOT lock specific versions during development. Use flexible version specs (e.g., `"fastapi"` not `"fastapi==0.115.0"`).

### Rationale
- Receive incoming fixes, security patches, and advances
- Rapidly-evolving libraries (FastAPI, Pydantic, psycopg v3) improve frequently
- Lock versions only when moving to QA/Production

### Implementation
- `poetry.lock` excluded from git during development
- Lock file generated and committed for QA/Production releases

---

## DD-006: Pluggable Embedding Provider Architecture

**Date:** December 28, 2025  
**Status:** Accepted  

### Context
The embedding service initially used OpenAI's embedding API exclusively with a fixed enum of model names. This had several issues:
- Required OpenAI API key (not always available/desired)
- Fixed set of models via Python enum
- No support for Anthropic's recommended embedding provider (Voyage AI)
- Model names hardcoded and inflexible

### Decision
Implement a pluggable embedding provider architecture with:
1. **Base provider interface** (`EmbeddingProvider` ABC)
2. **Provider registry** for dynamic registration
3. **String-based model IDs** instead of enums for flexibility
4. **Multiple provider support** with auto-detection

### Provider Architecture
```
embedding_providers/
├── __init__.py        # Exports public API
├── base.py            # EmbeddingProvider ABC, EmbeddingResult dataclass
├── registry.py        # Provider registration and lookup
├── voyage.py          # Voyage AI provider (Anthropic recommended)
└── openai.py          # OpenAI provider
```

### Provider Interface
```python
class EmbeddingProvider(ABC):
    @property
    def provider_name(self) -> str: ...
    def list_models(self) -> list[EmbeddingModelInfo]: ...
    def get_model_info(self, model_id: str) -> EmbeddingModelInfo | None: ...
    async def generate_embedding(self, text: str, model_id: str) -> EmbeddingResult: ...
    async def generate_embeddings_batch(self, texts: list[str], model_id: str) -> list[EmbeddingResult]: ...
    def is_configured(self) -> bool: ...
```

### Available Providers
| Provider | Models | API Key Env Var |
|----------|--------|-----------------|
| **Voyage AI** (preferred) | voyage-3, voyage-3-large, voyage-code-3, etc. | VOYAGE_API_KEY |
| OpenAI | text-embedding-3-small, text-embedding-3-large | OPENAI_API_KEY |

### Configuration
- `VOYAGE_API_KEY`: Voyage AI (Anthropic's recommended provider)
- `OPENAI_API_KEY`: OpenAI fallback
- `DEFAULT_EMBEDDING_MODEL`: Optional explicit default (auto-detected if not set)

### API Changes
- `GET /embeddings/providers` - List available providers and models
- Model parameter accepts string model ID (e.g., "voyage-3", "text-embedding-3-small")
- Uses configured default if model not specified

### Consequences
- Supports multiple embedding providers out of the box
- New providers can be added by implementing `EmbeddingProvider` interface
- Dynamic model discovery via API
- Voyage AI preferred when configured (Anthropic recommended)
- Graceful fallback to any configured provider
- No code changes needed to support new Voyage AI or OpenAI models
