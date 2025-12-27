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
- Alembic migrations target the `mimirdata` schema

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
├── id (uuid, PK)
├── slug (text, unique) -- e.g., "development", "systems_architecture"
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
├── id (uuid, PK)
├── tenant_id (uuid, FK → tenants.id, NOT NULL)  -- NEW
├── artifact_type (enum)
├── ...
```

### API Implications
- Tenant specified via header: `X-Tenant-ID: <uuid>` or `X-Tenant-Slug: <slug>`
- All queries automatically filtered by tenant
- Tenant context resolved at middleware level
- Default tenant configurable per environment

### Example Tenants
| slug | name | tenant_type |
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

## DD-003: SQL as Implementation Language (No ORM)

**Date:** December 26, 2025  
**Status:** Accepted  

### Context
We considered using SQLAlchemy ORM vs. raw SQL for data access.

### Decision
Use raw SQL via psycopg v3 for all data access. SQLAlchemy Core is used only for table definitions (to support Alembic autogenerate).

### Rationale
- API is request→SQL→response, not object-graph-centric
- PostgreSQL features (pgvector, FTS, recursive CTEs, JSONB) require raw SQL
- Schema is stable and deliberate, not rapidly evolving
- SQL is transparent about what the database actually does

### Consequences
- Queries written in `.sql` files or as SQL strings
- No lazy loading or relationship traversal magic
- Full control over query optimization
- Alembic autogenerate still works via SQLAlchemy Core metadata

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
