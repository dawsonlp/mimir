"""Mímir - Durable Memory & Meta-Analysis Storage System.

FastAPI application entry point with lifespan management.
"""

import logging
import sys
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

import structlog
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from mimir.config import get_settings
from mimir.database import close_pool, health_check, init_pool
from mimir.routers import (
    artifacts,
    decisions,
    embeddings,
    intents,
    provenance,
    relations,
    search,
    spans,
    tenants,
)
from mimir.services.embedding_providers.ollama import OllamaEmbeddingProvider
from mimir.services.embedding_providers.openai import OpenAIProvider
from mimir.services.embedding_providers.registry import (
    list_providers,
    register_provider,
)
from mimir.services.embedding_providers.voyage import VoyageProvider


def configure_logging(log_level: str) -> None:
    """Configure structured JSON logging.

    Sets up structlog with JSON formatting for machine parsing.
    Development mode can use pretty printing for readability.
    """
    # Configure standard library logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, log_level.upper()),
    )

    # Configure structlog processors
    processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    # Use JSON in production, console renderer in development
    settings = get_settings()
    if settings.environment == "development":
        processors.append(structlog.dev.ConsoleRenderer(colors=True))
    else:
        processors.append(structlog.processors.JSONRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, log_level.upper())
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler.

    Manages startup and shutdown of resources like database connections.
    """
    settings = get_settings()
    logger = structlog.get_logger()

    # Startup
    configure_logging(settings.log_level)
    await logger.ainfo(
        "Starting Mímir API",
        version=settings.api_version,
        environment=settings.environment,
    )

    # Initialize database pool
    await init_pool()
    await logger.ainfo("Database connection pool initialized")

    # Register embedding providers (order matters for default selection)
    # 1. Voyage AI - preferred when configured (Anthropic recommended)
    # 2. OpenAI - fallback for cloud embeddings
    # 3. Ollama - local embeddings, no API key needed
    register_provider(VoyageProvider())
    register_provider(OpenAIProvider())
    register_provider(OllamaEmbeddingProvider())
    await logger.ainfo(
        "Embedding providers registered",
        providers=list_providers(),
    )

    yield

    # Shutdown
    await logger.ainfo("Shutting down Mímir API")
    await close_pool()
    await logger.ainfo("Database connection pool closed")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title=settings.api_title,
        version=settings.api_version,
        description=(
            "Mímir - Durable Memory & Meta-Analysis Storage System. "
            "A storage API for conversations, documents, decisions, and intents "
            "with semantic search capabilities via pgvector."
        ),
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    # Register routes
    @app.get(
        "/health",
        tags=["Health"],
        summary="Health check endpoint",
        description="Check API and database health status.",
        response_description="Health status including database connectivity",
    )
    async def health_endpoint():
        """Check the health of the API and its dependencies.

        Returns:
            Health status including:
            - API status
            - Database connectivity
            - pgvector extension status
            - PostgreSQL version
        """
        db_health = await health_check()

        status = "healthy" if db_health["status"] == "healthy" else "unhealthy"
        status_code = 200 if status == "healthy" else 503

        return JSONResponse(
            status_code=status_code,
            content={
                "status": status,
                "timestamp": datetime.now(UTC).isoformat(),
                "version": settings.api_version,
                "components": {
                    "api": "healthy",
                    "database": db_health,
                },
            },
        )

    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        """Log all HTTP requests with timing and context."""
        import time
        import uuid

        request_id = str(uuid.uuid4())[:8]
        start_time = time.perf_counter()

        # Bind request context for all downstream logs
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        logger = structlog.get_logger()
        await logger.ainfo(
            "Request started",
            method=request.method,
            path=request.url.path,
        )

        response = await call_next(request)

        duration_ms = (time.perf_counter() - start_time) * 1000

        await logger.ainfo(
            "Request completed",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=round(duration_ms, 2),
        )

        # Add request ID to response headers for tracing
        response.headers["X-Request-ID"] = request_id

        return response

    # Register API routers
    app.include_router(tenants.router, prefix="/api/v1")
    app.include_router(artifacts.router, prefix="/api/v1")
    app.include_router(intents.router, prefix="/api/v1")
    app.include_router(decisions.router, prefix="/api/v1")
    app.include_router(spans.router, prefix="/api/v1")
    app.include_router(relations.router, prefix="/api/v1")
    app.include_router(search.router, prefix="/api/v1")
    app.include_router(embeddings.router, prefix="/api/v1")
    app.include_router(provenance.router, prefix="/api/v1")

    return app


# Create the app instance
app = create_app()
