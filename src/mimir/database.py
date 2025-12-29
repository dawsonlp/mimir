"""Database connection management for Mímir V2.

Uses psycopg v3 async with connection pooling.
SQL is the implementation language - NO ORM.
"""

import contextlib
from collections.abc import AsyncGenerator

from psycopg_pool import AsyncConnectionPool

from mimir.config import get_settings

# Module-level connection pool (initialized lazily)
_pool: AsyncConnectionPool | None = None


async def init_pool() -> AsyncConnectionPool:
    """Initialize the async connection pool.

    Call this during application startup (lifespan).
    """
    global _pool
    if _pool is not None:
        return _pool

    settings = get_settings()

    _pool = AsyncConnectionPool(
        conninfo=settings.database_url,
        min_size=2,
        max_size=10,
        open=False,  # Don't open immediately; we'll open explicitly
    )
    await _pool.open()
    return _pool


async def close_pool() -> None:
    """Close the connection pool.

    Call this during application shutdown (lifespan).
    """
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def get_pool() -> AsyncConnectionPool:
    """Get the connection pool.

    Raises RuntimeError if pool is not initialized.
    """
    if _pool is None:
        raise RuntimeError("Database pool not initialized. Call init_pool() first.")
    return _pool


@contextlib.asynccontextmanager
async def get_connection() -> AsyncGenerator:
    """Get a database connection from the pool.

    Usage:
        async with get_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT ...")
    """
    pool = get_pool()
    async with pool.connection() as conn:
        yield conn


async def health_check() -> dict:
    """Check database connectivity and return status.

    Returns a dict with connection status and details.
    """
    try:
        async with get_connection() as conn, conn.cursor() as cur:
            # Check basic connectivity
            await cur.execute("SELECT 1")
            await cur.fetchone()

            # Check pgvector extension
            await cur.execute(
                "SELECT extname FROM pg_extension WHERE extname = 'vector'"
            )
            pgvector_row = await cur.fetchone()
            pgvector_enabled = pgvector_row is not None

            # Get PostgreSQL version
            await cur.execute("SELECT version()")
            version_row = await cur.fetchone()
            pg_version = version_row[0] if version_row else "unknown"

        return {
            "status": "healthy",
            "database": "connected",
            "pgvector": "enabled" if pgvector_enabled else "disabled",
            "postgres_version": pg_version,
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "database": "disconnected",
            "error": str(e),
        }
