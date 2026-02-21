"""Unit tests for MimirClient.

Tests error mapping, URL construction, header injection, and model parsing
using respx to mock httpx requests.
"""

import pytest
import respx
import httpx

from mimir_client import (
    MimirClient,
    MimirClientSettings,
    MimirConnectionError,
    MimirConflictError,
    MimirError,
    MimirNotFoundError,
    MimirServerError,
    MimirValidationError,
    Artifact,
    ArtifactList,
    ArtifactType,
    EmbeddingType,
    HealthResponse,
    Relation,
    RelationType,
    SearchResponse,
    Tenant,
    TenantList,
)


# --- Fixtures ---


SAMPLE_TENANT = {
    "id": 1,
    "shortname": "dev",
    "name": "Development",
    "tenant_type": "environment",
    "description": None,
    "is_active": True,
    "metadata": {},
    "created_at": "2026-02-20T10:00:00Z",
    "updated_at": "2026-02-20T10:00:00Z",
}

SAMPLE_ARTIFACT = {
    "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "tenant_id": 1,
    "artifact_type_id": 1,
    "artifact_type": "document",
    "title": "Test Artifact",
    "content": "Test content",
    "source": None,
    "source_system": None,
    "external_id": None,
    "parent_artifact_id": None,
    "metadata": {},
    "created_at": "2026-02-20T10:00:00Z",
    "updated_at": "2026-02-20T10:00:00Z",
}

SAMPLE_ARTIFACT_TYPE = {
    "id": 1,
    "code": "document",
    "display_name": "Document",
    "description": None,
    "category": "content",
    "is_active": True,
    "sort_order": None,
    "created_at": "2026-02-20T10:00:00Z",
}

SAMPLE_RELATION_TYPE = {
    "id": 1,
    "code": "derived_from",
    "display_name": "Derived From",
    "description": None,
    "inverse_code": "source_of",
    "is_active": True,
    "sort_order": None,
    "created_at": "2026-02-20T10:00:00Z",
}

SAMPLE_RELATION = {
    "id": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
    "tenant_id": 1,
    "source_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "target_id": "c3d4e5f6-a7b8-9012-cdef-123456789012",
    "relation_type": "derived_from",
    "confidence": 0.95,
    "metadata": {},
    "created_at": "2026-02-20T10:00:00Z",
}

SAMPLE_EMBEDDING_TYPE = {
    "id": 1,
    "code": "nomic",
    "display_name": "Nomic",
    "provider": "ollama",
    "model_name": "nomic-embed-text",
    "dimensions": 768,
    "is_active": True,
    "created_at": "2026-02-20T10:00:00Z",
}

SAMPLE_SEARCH_RESPONSE = {
    "results": [
        {
            "artifact": SAMPLE_ARTIFACT,
            "score": 0.85,
            "rank": 1,
        }
    ],
    "strategy": "fulltext",
    "total": 1,
    "limit": 20,
    "offset": 0,
}

SAMPLE_HEALTH = {
    "status": "healthy",
    "version": "5.0.1",
}


# --- Construction & Configuration ---


class TestClientConstruction:
    def test_default_construction(self):
        client = MimirClient()
        assert client.tenant_id is None
        assert client._api_url == "http://localhost:38000"

    def test_construction_with_params(self):
        client = MimirClient(api_url="http://api:8000", tenant_id=5, timeout=60.0)
        assert client.tenant_id == 5
        assert client._api_url == "http://api:8000"
        assert "X-Tenant-ID" in client._client.headers
        assert client._client.headers["X-Tenant-ID"] == "5"

    def test_trailing_slash_stripped(self):
        client = MimirClient(api_url="http://api:8000/")
        assert client._api_url == "http://api:8000"

    def test_from_settings(self):
        settings = MimirClientSettings(api_url="http://test:9000", tenant_id=3, timeout=15.0)
        client = MimirClient.from_settings(settings)
        assert client.tenant_id == 3
        assert client._api_url == "http://test:9000"

    def test_tenant_id_property_setter(self):
        client = MimirClient(tenant_id=1)
        assert client.tenant_id == 1
        client.tenant_id = 2
        assert client.tenant_id == 2
        assert client._client.headers["X-Tenant-ID"] == "2"

    def test_tenant_id_set_to_none(self):
        client = MimirClient(tenant_id=1)
        client.tenant_id = None
        assert client.tenant_id is None
        assert "X-Tenant-ID" not in client._client.headers


# --- Error Mapping ---


class TestErrorMapping:
    @respx.mock
    @pytest.mark.asyncio
    async def test_404_raises_not_found(self):
        respx.get("http://localhost:38000/tenants/999").mock(
            return_value=httpx.Response(404, json={"detail": "Tenant not found"})
        )
        async with MimirClient(tenant_id=1) as client:
            with pytest.raises(MimirNotFoundError, match="Tenant not found"):
                await client.get_tenant(999)

    @respx.mock
    @pytest.mark.asyncio
    async def test_409_raises_conflict(self):
        respx.post("http://localhost:38000/relations").mock(
            return_value=httpx.Response(409, json={"detail": "Relation already exists"})
        )
        async with MimirClient(tenant_id=1) as client:
            with pytest.raises(MimirConflictError, match="Relation already exists"):
                await client.create_relation("a" * 36, "b" * 36, "derived_from")

    @respx.mock
    @pytest.mark.asyncio
    async def test_422_raises_validation(self):
        respx.post("http://localhost:38000/artifacts").mock(
            return_value=httpx.Response(422, json={"detail": "Validation error"})
        )
        async with MimirClient(tenant_id=1) as client:
            with pytest.raises(MimirValidationError, match="Validation error"):
                await client.create_artifact("bad_type")

    @respx.mock
    @pytest.mark.asyncio
    async def test_500_raises_server_error(self):
        respx.get("http://localhost:38000/health").mock(
            return_value=httpx.Response(500, json={"detail": "Internal server error"})
        )
        async with MimirClient(tenant_id=1) as client:
            with pytest.raises(MimirServerError, match="Internal server error"):
                await client.health()

    @respx.mock
    @pytest.mark.asyncio
    async def test_other_4xx_raises_mimir_error(self):
        respx.get("http://localhost:38000/tenants/1").mock(
            return_value=httpx.Response(403, json={"detail": "Forbidden"})
        )
        async with MimirClient(tenant_id=1) as client:
            with pytest.raises(MimirError, match="HTTP 403"):
                await client.get_tenant(1)


# --- Tenant Methods ---


class TestTenantMethods:
    @respx.mock
    @pytest.mark.asyncio
    async def test_create_tenant(self):
        respx.post("http://localhost:38000/tenants").mock(
            return_value=httpx.Response(201, json=SAMPLE_TENANT)
        )
        async with MimirClient() as client:
            tenant = await client.create_tenant("dev", "Development")
            assert isinstance(tenant, Tenant)
            assert tenant.shortname == "dev"
            assert tenant.id == 1

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_tenant(self):
        respx.get("http://localhost:38000/tenants/1").mock(
            return_value=httpx.Response(200, json=SAMPLE_TENANT)
        )
        async with MimirClient(tenant_id=1) as client:
            tenant = await client.get_tenant(1)
            assert isinstance(tenant, Tenant)
            assert tenant.name == "Development"

    @respx.mock
    @pytest.mark.asyncio
    async def test_list_tenants(self):
        respx.get("http://localhost:38000/tenants").mock(
            return_value=httpx.Response(200, json={"items": [SAMPLE_TENANT], "total": 1})
        )
        async with MimirClient() as client:
            result = await client.list_tenants()
            assert isinstance(result, TenantList)
            assert result.total == 1
            assert len(result.items) == 1

    @respx.mock
    @pytest.mark.asyncio
    async def test_delete_tenant_returns_none(self):
        respx.delete("http://localhost:38000/tenants/1").mock(
            return_value=httpx.Response(204)
        )
        async with MimirClient() as client:
            result = await client.delete_tenant(1)
            assert result is None

    @respx.mock
    @pytest.mark.asyncio
    async def test_ensure_tenant_finds_existing(self):
        respx.get("http://localhost:38000/tenants/by-shortname/dev").mock(
            return_value=httpx.Response(200, json=SAMPLE_TENANT)
        )
        async with MimirClient() as client:
            tenant = await client.ensure_tenant("dev", "Development")
            assert tenant.id == 1
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
            assert client.tenant_id == 2


# --- Artifact Methods ---


class TestArtifactMethods:
    @respx.mock
    @pytest.mark.asyncio
    async def test_create_artifact(self):
        respx.post("http://localhost:38000/artifacts").mock(
            return_value=httpx.Response(201, json=SAMPLE_ARTIFACT)
        )
        async with MimirClient(tenant_id=1) as client:
            artifact = await client.create_artifact(
                "document", title="Test Artifact", content="Test content"
            )
            assert isinstance(artifact, Artifact)
            assert artifact.title == "Test Artifact"
            assert artifact.artifact_type == "document"

    @respx.mock
    @pytest.mark.asyncio
    async def test_list_artifacts(self):
        respx.get("http://localhost:38000/artifacts").mock(
            return_value=httpx.Response(
                200, json={"items": [SAMPLE_ARTIFACT], "total": 1}
            )
        )
        async with MimirClient(tenant_id=1) as client:
            result = await client.list_artifacts(artifact_type="document")
            assert isinstance(result, ArtifactList)
            assert result.total == 1


# --- Search Methods ---


class TestSearchMethods:
    @respx.mock
    @pytest.mark.asyncio
    async def test_search_fulltext(self):
        respx.post("http://localhost:38000/search").mock(
            return_value=httpx.Response(200, json=SAMPLE_SEARCH_RESPONSE)
        )
        async with MimirClient(tenant_id=1) as client:
            result = await client.search_fulltext("test query")
            assert isinstance(result, SearchResponse)
            assert result.strategy == "fulltext"
            assert len(result.results) == 1
            assert result.results[0].score == 0.85

    @respx.mock
    @pytest.mark.asyncio
    async def test_unified_search(self):
        respx.post("http://localhost:38000/search").mock(
            return_value=httpx.Response(200, json=SAMPLE_SEARCH_RESPONSE)
        )
        async with MimirClient(tenant_id=1) as client:
            result = await client.search(query="test", limit=10)
            assert isinstance(result, SearchResponse)
            assert result.total == 1


# --- Health Methods ---


class TestHealthMethods:
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
            assert h.version == "5.0.1"

    @respx.mock
    @pytest.mark.asyncio
    async def test_is_healthy_true(self):
        respx.get("http://localhost:38000/health").mock(
            return_value=httpx.Response(200, json=SAMPLE_HEALTH)
        )
        async with MimirClient() as client:
            assert await client.is_healthy() is True

    @respx.mock
    @pytest.mark.asyncio
    async def test_is_healthy_false_on_error(self):
        respx.get("http://localhost:38000/health").mock(
            return_value=httpx.Response(500, json={"detail": "down"})
        )
        async with MimirClient() as client:
            assert await client.is_healthy() is False


# --- Header Injection ---


class TestHeaderInjection:
    @respx.mock
    @pytest.mark.asyncio
    async def test_tenant_header_sent(self):
        route = respx.get("http://localhost:38000/tenants/1").mock(
            return_value=httpx.Response(200, json=SAMPLE_TENANT)
        )
        async with MimirClient(tenant_id=42) as client:
            await client.get_tenant(1)
            assert route.calls[0].request.headers["X-Tenant-ID"] == "42"

    @respx.mock
    @pytest.mark.asyncio
    async def test_no_tenant_header_when_none(self):
        route = respx.get("http://localhost:38000/tenants/1").mock(
            return_value=httpx.Response(200, json=SAMPLE_TENANT)
        )
        async with MimirClient(tenant_id=None) as client:
            await client.get_tenant(1)
            assert "X-Tenant-ID" not in route.calls[0].request.headers
