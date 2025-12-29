"""Mímir V2 - FastAPI application."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from mimir.config import settings
from mimir.database import close_pool, init_pool
from mimir.routers import (
    artifact_types,
    artifacts,
    embeddings,
    provenance,
    relation_types,
    relations,
    search,
    tenants,
)

# Import to trigger provider registration
from mimir.services import embedding_providers  # noqa: F401

# OpenAPI description with entity overview
API_DESCRIPTION = """
# Mímir V2 - Knowledge Graph & Semantic Memory API

Mímir stores and retrieves knowledge using a unified artifact model with semantic search.

## Entity Overview

```
TENANT → owns → ARTIFACT → has → ARTIFACT_VERSION
                   │
                   ├── connected via → RELATION
                   ├── searchable via → EMBEDDING  
                   └── tracked by → PROVENANCE_EVENT
```

## Core Entities

### Tenant
Multi-tenancy isolation. Every API call requires `X-Tenant-ID` header.
- Types: `user`, `organization`, `system`

### Artifact
Universal knowledge unit. Everything is an artifact.
- **Content types:** conversation, document, note
- **Positional types:** chunk, quote, highlight, annotation (with start_offset/end_offset)
- **Derived types:** intent, decision, analysis, summary, finding, question, answer

### Artifact Version
Immutable snapshots. Created automatically on artifact update.

### Relation
Knowledge graph edges connecting artifacts.
- Types: `references`, `supports`, `contradicts`, `derived_from`, `supersedes`, `parent_of`, `child_of`, `implements`, `resolves`, `related_to`
- Each type has an inverse (e.g., `references` ↔ `referenced_by`)

### Embedding
Vector representations for semantic search.
- Models: OpenAI (`text-embedding-3-small/large`), Ollama (`nomic-embed-text`, `mxbai-embed-large`)
- HNSW index for fast approximate nearest neighbor

### Provenance Event
Immutable audit trail.
- Actions: `create`, `update`, `delete`, `supersede`, `archive`, `restore`
- Actors: `user`, `system`, `llm`, `api_client`, `migration`

## Common Workflows

**Create decision from intent:**
1. `POST /artifacts` with `artifact_type=intent`
2. `POST /artifacts` with `artifact_type=decision`
3. `POST /relations` linking decision → intent with `relation_type=resolves`

**Semantic search:**
1. `POST /embeddings` to embed artifacts
2. `POST /search/semantic` or `POST /search/hybrid` to find similar
"""

# Tag descriptions for Swagger UI
TAGS_METADATA = [
    {
        "name": "tenants",
        "description": "**Multi-tenancy isolation.** Each tenant has completely isolated data. All other endpoints require `X-Tenant-ID` header.",
    },
    {
        "name": "artifact-types",
        "description": "**Vocabulary management** for artifact types. Categories: content (conversation, document, note), positional (chunk, quote, highlight), derived (intent, decision, analysis, summary).",
    },
    {
        "name": "artifacts",
        "description": "**Universal knowledge units.** All knowledge is stored as artifacts with type discrimination. Supports hierarchy via `parent_artifact_id` and positional data via `start_offset`/`end_offset`.",
    },
    {
        "name": "relation-types",
        "description": "**Vocabulary management** for relation types. Each relation has an inverse (e.g., `parent_of` ↔ `child_of`). Some are symmetric (`contradicts`, `related_to`).",
    },
    {
        "name": "relations",
        "description": "**Knowledge graph edges** connecting artifacts and versions. Query incoming, outgoing, or both directions. Use for lineage tracking, evidence linking, and hierarchies.",
    },
    {
        "name": "embeddings",
        "description": "**Vector representations** for semantic search. Supports OpenAI and Ollama models. Use chunk_index for multi-vector documents.",
    },
    {
        "name": "search",
        "description": "**Find knowledge.** Full-text search (tsvector), semantic search (pgvector), and hybrid search (RRF algorithm combining both).",
    },
    {
        "name": "provenance",
        "description": "**Immutable audit trail.** Tracks who did what, when, and why. Query by entity or actor. Append-only for compliance.",
    },
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown."""
    await init_pool()
    yield
    await close_pool()


app = FastAPI(
    title="Mímir V2",
    description=API_DESCRIPTION,
    version="2.0.0",
    lifespan=lifespan,
    openapi_tags=TAGS_METADATA,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(tenants.router)
app.include_router(artifact_types.router)
app.include_router(artifacts.router)
app.include_router(relation_types.router)
app.include_router(relations.router)
app.include_router(embeddings.router)
app.include_router(search.router)
app.include_router(provenance.router)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "version": "2.0.0"}


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": "Mímir V2",
        "version": "2.0.0",
        "docs": "/docs",
        "openapi": "/openapi.json",
    }
