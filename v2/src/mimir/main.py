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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown."""
    await init_pool()
    yield
    await close_pool()


app = FastAPI(
    title="Mímir V2",
    description="Knowledge graph and semantic memory API",
    version="2.0.0",
    lifespan=lifespan,
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
