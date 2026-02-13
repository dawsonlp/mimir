"""Pytest configuration and fixtures for mimir_semantic tests.

Fixtures
--------
client : MimirClient
    Configured client from environment (async)
test_tenant : dict
    Creates a test tenant for isolation
"""

import os
from uuid import uuid4

import pytest

# Set test environment defaults if not set
os.environ.setdefault("MIMIR_API_URL", "http://localhost:38000")


@pytest.fixture
def api_url():
    """Get API URL from environment."""
    return os.environ.get("MIMIR_API_URL", "http://localhost:38000")


@pytest.fixture
async def client():
    """Provides configured MimirClient for tests.
    
    Reads configuration from environment. Use with async tests.
    
    Example
    -------
    >>> async def test_health(client):
    ...     health = await client.health()
    ...     assert health["status"] == "healthy"
    """
    from mimir_semantic import MimirClient
    
    client = MimirClient.from_env()
    yield client
    await client.close()


@pytest.fixture
async def test_tenant(client):
    """Creates a unique test tenant for isolation.
    
    Each test gets a fresh tenant with a random shortname.
    Tenant persists after test (append-only storage).
    
    Example
    -------
    >>> async def test_with_tenant(client, test_tenant):
    ...     client.tenant_id = test_tenant["id"]
    ...     artifact = await client.create_artifact(...)
    """
    tenant = await client.create_tenant(
        shortname=f"test-{uuid4().hex[:8]}",
        name="Test Tenant",
        tenant_type="experiment",
    )
    # Update client with new tenant ID
    client.tenant_id = tenant["id"]
    yield tenant
    # No cleanup - tenants are append-only