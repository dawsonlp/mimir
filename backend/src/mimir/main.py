"""Mímir V4 - FastAPI application."""

from contextlib import asynccontextmanager

import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse

from mimir.config import settings
from mimir.database import close_pool, init_pool
from mimir.routers import (
    artifact_types,
    artifacts,
    context,
    embedding_types,
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
# Mímir V4 - Knowledge Graph & Semantic Memory API

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

### Embedding Type
Vocabulary table for embedding models. Each type creates a dedicated vector table.
- Providers: OpenAI, Ollama, Voyage
- Each type has fixed dimensions for proper HNSW indexing

### Embedding
Vector representations for semantic search.
- Uses multi-table architecture (one vector table per embedding type)
- Each type has its own HNSW index
- Requires `embedding_type` to be registered first

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
1. `POST /embedding-types` to register model (creates vector table)
2. `POST /embeddings` to embed artifacts
3. `POST /embeddings/similar` or `POST /search/semantic` to find similar
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
        "name": "context",
        "description": "**RAG context retrieval.** Policy-driven context assembly for RAG applications. Single request retrieves artifact with all contextually relevant artifacts. Policies: direct_relations, derived_lineage, evidence_chain, full_graph.",
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
        "name": "embedding-types",
        "description": "**Embedding model vocabulary.** Register new embedding types to create vector tables. Each type has fixed dimensions and HNSW index.",
    },
    {
        "name": "embeddings",
        "description": "**Vector representations** for semantic search. Supports multiple models via embedding_type. Each embedding type has its own optimized vector table.",
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
    title="Mímir V4",
    description=API_DESCRIPTION,
    version="4.0.1",
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
app.include_router(context.router)
app.include_router(relation_types.router)
app.include_router(relations.router)
app.include_router(embedding_types.router)
app.include_router(embeddings.router)
app.include_router(search.router)
app.include_router(provenance.router)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Return structured JSON for unhandled exceptions instead of plain text 500."""
    logging.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc), "code": "INTERNAL_ERROR"},
    )


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "version": "4.0.1"}


# HTML landing page template
LANDING_PAGE_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Mímir V4 - Knowledge Graph API</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
            min-height: 100vh;
            color: #e8e8e8;
            display: flex;
            flex-direction: column;
            align-items: center;
            padding: 40px 20px;
        }
        .header {
            text-align: center;
            margin-bottom: 50px;
        }
        .logo {
            font-size: 4rem;
            margin-bottom: 10px;
        }
        h1 {
            font-size: 2.5rem;
            font-weight: 300;
            margin-bottom: 10px;
            color: #fff;
        }
        .version {
            font-size: 1rem;
            color: #94a3b8;
            background: rgba(255,255,255,0.1);
            padding: 4px 12px;
            border-radius: 20px;
            display: inline-block;
        }
        .tagline {
            font-size: 1.1rem;
            color: #94a3b8;
            margin-top: 15px;
        }
        .cards {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 20px;
            max-width: 900px;
            width: 100%;
        }
        .card {
            background: rgba(255,255,255,0.05);
            border: 1px solid rgba(255,255,255,0.1);
            border-radius: 12px;
            padding: 25px;
            text-decoration: none;
            color: inherit;
            transition: all 0.3s ease;
        }
        .card:hover {
            background: rgba(255,255,255,0.1);
            border-color: rgba(255,255,255,0.2);
            transform: translateY(-2px);
        }
        .card-icon {
            font-size: 2rem;
            margin-bottom: 15px;
        }
        .card h2 {
            font-size: 1.3rem;
            font-weight: 500;
            margin-bottom: 8px;
            color: #fff;
        }
        .card p {
            font-size: 0.9rem;
            color: #94a3b8;
            line-height: 1.5;
        }
        .card .path {
            font-family: 'SF Mono', Monaco, monospace;
            font-size: 0.8rem;
            color: #60a5fa;
            margin-top: 12px;
            display: block;
        }
        .status {
            margin-top: 50px;
            text-align: center;
            color: #94a3b8;
            font-size: 0.9rem;
        }
        .status-dot {
            display: inline-block;
            width: 8px;
            height: 8px;
            background: #22c55e;
            border-radius: 50%;
            margin-right: 8px;
            animation: pulse 2s infinite;
        }
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }
        footer {
            margin-top: auto;
            padding-top: 40px;
            color: #64748b;
            font-size: 0.85rem;
        }
    </style>
</head>
<body>
    <div class="header">
        <div class="logo">🧠</div>
        <h1>Mímir V4</h1>
        <span class="version">v4.0.1</span>
        <p class="tagline">Knowledge Graph &amp; Semantic Memory API</p>
    </div>
    
    <div class="cards">
        <a href="/docs" class="card">
            <div class="card-icon">📚</div>
            <h2>Swagger UI</h2>
            <p>Interactive API explorer. Try out requests directly in your browser with full request/response details.</p>
            <span class="path">/docs</span>
        </a>
        
        <a href="/redoc" class="card">
            <div class="card-icon">📖</div>
            <h2>ReDoc</h2>
            <p>Clean, readable API documentation with detailed schemas and examples.</p>
            <span class="path">/redoc</span>
        </a>
        
        <a href="/openapi.json" class="card">
            <div class="card-icon">📋</div>
            <h2>OpenAPI Spec</h2>
            <p>Raw OpenAPI 3.0 specification in JSON format for code generation and tooling.</p>
            <span class="path">/openapi.json</span>
        </a>
        
        <a href="/health" class="card">
            <div class="card-icon">💚</div>
            <h2>Health Check</h2>
            <p>Service health status endpoint for monitoring and orchestration.</p>
            <span class="path">/health</span>
        </a>
    </div>
    
    <div class="status">
        <span class="status-dot"></span>
        API is running
    </div>
    
    <footer>
        Mímir — Norse god of wisdom and knowledge
    </footer>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def root():
    """Landing page with links to documentation."""
    return LANDING_PAGE_HTML
