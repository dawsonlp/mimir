"""Unit tests for MimirClient (async).

Mirrors sync client tests with async/await patterns using respx.
"""

import httpx
import pytest
import respx

from mimir_client import (
    HealthResponse,
    MimirClient,
    MimirClientSettings,
    MimirTenantError,
)

SAMPLE_TENANT = {
    "id": 1,
    "shortname": "dev",
    "name": "Development",
    "tenant_type": "environment",
    "description": None,
    "is_active": True,
    "metadata": {},
    "created_at": "2026-02-20T10:00:00Z",
}

SAMPLE_HEALTH = {
    "status": "healthy",
    "version": "5.0.1",
}


class TestAsyncClientConstruction:
    def test_construction_with_tenant_shortname(self):
        client = MimirClient(tenant="rademo1")
        assert client.tenant == "rademo1"
        assert client.tenant_id is None

    def test_construction_with_tenant_id_deprecated(self):
        with pytest.warns(DeprecationWarning, match="tenant_id parameter is deprecated"):
            client = MimirClient(tenant_id=5)
        assert client.tenant is None
        assert client.tenant_id == 5

    def test_construction_with_both_raises_value_error(self):
        with pytest.raises(ValueError, match="Cannot provide both"):
            MimirClient(tenant="dev", tenant_id=1)

    def test_construction_with_neither(self):
        client = MimirClient()
        assert client.tenant is None
        assert client.tenant_id is None

    def test_from_settings_with_tenant(self):
        settings = MimirClientSettings(api_url="http://test:9000", tenant="rademo1")
        client = MimirClient.from_settings(settings)
        assert client.tenant == "rademo1"
        assert client.tenant_id is None


class TestAsyncClientProperties:
    def test_tenant_setter_clears_resolution_cache(self):
        with pytest.warns(DeprecationWarning):
            client = MimirClient(tenant_id=1)
        client.tenant = "newshortname"
        assert client.tenant == "newshortname"
        assert client.tenant_id is None

    def test_tenant_id_setter_deprecated_clears_tenant(self):
        client = MimirClient(tenant="dev")
        with pytest.warns(DeprecationWarning, match="tenant_id is deprecated"):
            client.tenant_id = 42
        assert client.tenant is None
        assert client.tenant_id == 42


class TestAsyncLazyResolution:
    @respx.mock
    @pytest.mark.asyncio
    async def test_first_request_resolves_shortname(self):
        respx.get("http://localhost:38000/tenants/by-shortname/rademo1").mock(
            return_value=httpx.Response(200, json=SAMPLE_TENANT)
        )
        respx.get("http://localhost:38000/health").mock(
            return_value=httpx.Response(200, json=SAMPLE_HEALTH)
        )
        async with MimirClient(tenant="rademo1") as client:
            await client.health()
            assert client.tenant_id == 1
            assert client._client.headers["X-Tenant-ID"] == "1"

    @respx.mock
    @pytest.mark.asyncio
    async def test_second_request_reuses_cached_integer(self):
        resolve_route = respx.get("http://localhost:38000/tenants/by-shortname/rademo1").mock(
            return_value=httpx.Response(200, json=SAMPLE_TENANT)
        )
        respx.get("http://localhost:38000/health").mock(
            return_value=httpx.Response(200, json=SAMPLE_HEALTH)
        )
        async with MimirClient(tenant="rademo1") as client:
            await client.health()
            await client.health()
            assert resolve_route.call_count == 1

    @respx.mock
    @pytest.mark.asyncio
    async def test_unknown_shortname_raises_tenant_error(self):
        respx.get("http://localhost:38000/tenants/by-shortname/nonexistent").mock(
            return_value=httpx.Response(404, json={"detail": "Not found"})
        )
        respx.get("http://localhost:38000/health").mock(
            return_value=httpx.Response(200, json=SAMPLE_HEALTH)
        )
        async with MimirClient(tenant="nonexistent") as client:
            with pytest.raises(MimirTenantError, match="not found"):
                await client.health()

    @respx.mock
    @pytest.mark.asyncio
    async def test_no_resolution_when_no_tenant_set(self):
        resolve_route = respx.get(url__regex=r".*/tenants/by-shortname/.*").mock(
            return_value=httpx.Response(200, json=SAMPLE_TENANT)
        )
        respx.get("http://localhost:38000/health").mock(
            return_value=httpx.Response(200, json=SAMPLE_HEALTH)
        )
        async with MimirClient() as client:
            h = await client.health()
            assert h.status == "healthy"
            assert resolve_route.call_count == 0


class TestAsyncEnsureTenant:
    @respx.mock
    @pytest.mark.asyncio
    async def test_ensure_tenant_finds_existing(self):
        respx.get("http://localhost:38000/tenants/by-shortname/dev").mock(
            return_value=httpx.Response(200, json=SAMPLE_TENANT)
        )
        async with MimirClient() as client:
            tenant = await client.ensure_tenant("dev", "Development")
            assert tenant.id == 1
            assert client.tenant == "dev"
            assert client.tenant_id == 1

    @respx.mock
    @pytest.mark.asyncio
    async def test_ensure_tenant_creates_new(self):
        respx.get("http://localhost:38000/tenants/by-shortname/new").mock(
            return_value=httpx.Response(404, json={"detail": "Not found"})
        )
        new_tenant = {**SAMPLE_TENANT, "id": 2, "shortname": "new", "name": "New Tenant"}
        respx.post("http://localhost:38000/tenants").mock(
            return_value=httpx.Response(201, json=new_tenant)
        )
        async with MimirClient() as client:
            tenant = await client.ensure_tenant("new", "New Tenant")
            assert tenant.id == 2
            assert client.tenant == "new"
            assert client.tenant_id == 2


class TestAsyncHealth:
    @respx.mock
    @pytest.mark.asyncio
    async def test_health(self):
        respx.get("http://localhost:38000/health").mock(
            return_value=httpx.Response(200, json=SAMPLE_HEALTH)
        )
        async with MimirClient() as client:
            h = await client.health()
            assert isinstance(h, HealthResponse)
            assert h.status == "healthy"

    @respx.mock
    @pytest.mark.asyncio
    async def test_is_healthy_false_on_error(self):
        respx.get("http://localhost:38000/health").mock(
            return_value=httpx.Response(500, json={"detail": "down"})
        )
        async with MimirClient() as client:
            assert await client.is_healthy() is False
