"""
Mímir V2 Test Configuration

Pytest fixtures for unit and integration testing.
Uses testcontainers for PostgreSQL with pgvector in integration tests.
"""

import os
from collections.abc import AsyncGenerator, Generator
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# Set test environment before importing app
os.environ.setdefault("TESTING", "true")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test")


@pytest.fixture(scope="session")
def anyio_backend():
    """Use asyncio for async tests."""
    return "asyncio"


@pytest.fixture
def test_tenant_data() -> dict[str, Any]:
    """Sample tenant data for tests."""
    return {
        "shortname": "test-tenant",
        "name": "Test Tenant",
        "tenant_type": "environment",
        "description": "A test tenant",
    }


@pytest.fixture
def test_artifact_type_data() -> dict[str, Any]:
    """Sample artifact type data for tests."""
    return {
        "code": "test_type",
        "display_name": "Test Type",
        "description": "A test artifact type",
        "category": "derived",
        "is_active": True,
        "sort_order": 100,
    }


@pytest.fixture
def test_artifact_data() -> dict[str, Any]:
    """Sample artifact data for tests."""
    return {
        "artifact_type": "document",
        "title": "Test Document",
        "content": "This is test content for the document.",
        "source": "test",
        "metadata": {"test_key": "test_value"},
    }


@pytest.fixture
def test_relation_data() -> dict[str, Any]:
    """Sample relation data for tests."""
    return {
        "source_type": "artifact",
        "source_id": 1,
        "target_type": "artifact",
        "target_id": 2,
        "relation_type": "references",
        "metadata": {},
    }


# Integration test fixtures (require running database)


@pytest_asyncio.fixture
async def async_client() -> AsyncGenerator[AsyncClient]:
    """
    Async HTTP client for API integration tests.

    Requires the API to be running (use docker compose up).
    """
    async with AsyncClient(
        base_url="http://localhost:38000",
        timeout=30.0,
    ) as client:
        yield client


@pytest_asyncio.fixture
async def app_client() -> AsyncGenerator[AsyncClient]:
    """
    Test client using ASGI transport (in-process testing).

    This imports the app directly, so database must be available.
    """
    from mimir.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


# Testcontainers fixture for isolated database testing


@pytest.fixture(scope="session")
def postgres_container() -> Generator[Any]:
    """
    PostgreSQL container with pgvector for isolated integration tests.

    Uses testcontainers to spin up a fresh database for each test session.
    """
    try:
        from testcontainers.postgres import PostgresContainer
    except ImportError:
        pytest.skip("testcontainers not installed")
        return

    # Use our custom postgres image with pgvector
    with PostgresContainer(
        image="dawsonlp/mimir-postgres:latest",
        username="test",
        password="test",
        dbname="testdb",
    ) as postgres:
        yield postgres


@pytest.fixture
def database_url(postgres_container) -> str:
    """Get connection URL from testcontainer."""
    return postgres_container.get_connection_url().replace(
        "postgresql+psycopg2://", "postgresql://"
    )
