"""Unit tests for MimirSyncClient.

Tests error mapping, URL construction, header injection, context manager,
model parsing, tenant shortname resolution, and deprecation warnings using
respx to mock httpx requests.

Test fixtures match the actual server response schemas.
"""


import httpx
import pytest
import respx

from mimir_client import (
    Artifact,
    ArtifactList,
    HealthResponse,
    MimirClientSettings,
    MimirConflictError,
    MimirError,
    MimirNotFoundError,
    MimirServerError,
    MimirSyncClient,
    MimirTenantError,
    MimirValidationError,
    SearchResponse,
    Tenant,
    TenantList,
)

# --- Fixtures matching actual server response schemas ---


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

SAMPLE_TENANT_MINIMAL = {
    "id": 2,
    "shortname": "test",
    "name": "Test",
    "created_at": "2026-02-20T10:00:00Z",
}

SAMPLE_ARTIFACT = {
    "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "tenant_id": 1,
    "artifact_type": "document",
    "title": "Test Artifact",
    "content": "Test content",
    "source": None,
    "source_system": None,
    "external_id": None,
    "parent_artifact_id": None,
    "metadata": {},
    "content_hash": "abc123",
    "created_at": "2026-02-20T10:00:00Z",
}

SAMPLE_ARTIFACT_TYPE = {
    "code": "document",
    "display_name": "Document",
    "description": None,
    "category": "content",
    "is_active": True,
    "sort_order": 0,
    "created_at": "2026-02-20T10:00:00Z",
}

SAMPLE_RELATION_TYPE = {
    "code": "derived_from",
    "display_name": "Derived From",
    "description": None,
    "inverse_code": "source_of",
    "is_symmetric": False,
    "is_active": True,
    "sort_order": 0,
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
    "code": "nomic-embed-text",
    "display_name": "Nomic Embed Text",
    "provider": "ollama",
    "dimensions": 768,
    "distance_metric": "cosine",
    "max_tokens": None,
    "description": None,
    "vector_table_name": "vec_nomic_embed_text",
    "is_active": True,
    "sort_order": 0,
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
    "total": 1,
    "query": "test query",
    "strategy": "fulltext",
}

SAMPLE_HEALTH = {
    "status": "healthy",
    "version": "5.0.1",
}


# --- Construction: tenant shortname (new primary path) ---


class TestSyncClientConstruction:
    def test_construction_with_tenant_shortname(self):
        client = MimirSyncClient(tenant="rademo1")
        assert client.tenant == "rademo1"
        assert client.tenant_id is None
        assert "X-Tenant-ID" not in client._client.headers

    def test_construction_with_tenant_id_deprecated(self):
        with pytest.warns(DeprecationWarning, match="tenant_id parameter is deprecated"):
            client = MimirSyncClient(tenant_id=5)
        assert client.tenant is None
        assert client.tenant_id == 5
        assert client._client.headers["X-Tenant-ID"] == "5"

    def test_construction_with_both_raises_value_error(self):
        with pytest.raises(ValueError, match="Cannot provide both"):
            MimirSyncClient(tenant="dev", tenant_id=1)

    def test_construction_with_neither(self):
        client = MimirSyncClient()
        assert client.tenant is None
        assert client.tenant_id is None
        assert "X-Tenant-ID" not in client._client.headers

    def test_default_api_url(self):
        client = MimirSyncClient()
        assert client._api_url == "http://localhost:38000"

    def test_custom_api_url(self):
        client = MimirSyncClient(api_url="http://api:8000")
        assert client._api_url == "http://api:8000"

    def test_trailing_slash_stripped(self):
        client = MimirSyncClient(api_url="http://api:8000/")
        assert client._api_url == "http://api:8000"

    def test_from_settings_with_tenant(self):
        settings = MimirClientSettings(api_url="http://test:9000", tenant="rademo1", timeout=15.0)
        client = MimirSyncClient.from_settings(settings)
        assert client.tenant == "rademo1"
        assert client.tenant_id is None

    def test_from_settings_with_tenant_id_deprecated(self):
        with pytest.warns(DeprecationWarning):
            settings = MimirClientSettings(api_url="http://test:9000", tenant_id=3, timeout=15.0)
        with pytest.warns(DeprecationWarning):
            client = MimirSyncClient.from_settings(settings)
        assert client.tenant_id == 3


# --- Properties ---


class TestSyncClientProperties:
    def test_tenant_setter_clears_resolution_cache(self):
        with pytest.warns(DeprecationWarning):
            client = MimirSyncClient(tenant_id=1)
        assert client.tenant_id == 1
        # Setting tenant clears the resolved integer
        client.tenant = "newshortname"
        assert client.tenant == "newshortname"
        assert client.tenant_id is None
        assert "X-Tenant-ID" not in client._client.headers

    def test_tenant_setter_to_none_removes_header(self):
        with pytest.warns(DeprecationWarning):
            client = MimirSyncClient(tenant_id=1)
        client.tenant = None
        assert client.tenant is None
        assert client.tenant_id is None
        assert "X-Tenant-ID" not in client._client.headers

    def test_tenant_id_setter_deprecated_clears_tenant(self):
        client = MimirSyncClient(tenant="dev")
        with pytest.warns(DeprecationWarning, match="tenant_id is deprecated"):
            client.tenant_id = 42
        assert client.tenant is None
        assert client.tenant_id == 42
        assert client._client.headers["X-Tenant-ID"] == "42"

    def test_tenant_id_setter_to_none(self):
        with pytest.warns(DeprecationWarning):
            client = MimirSyncClient(tenant_id=1)
        with pytest.warns(DeprecationWarning):
            client.tenant_id = None
        assert client.tenant_id is None
        assert "X-Tenant-ID" not in client._client.headers


# --- Lazy Resolution ---


class TestSyncLazyResolution:
    @respx.mock
    def test_first_request_resolves_shortname(self):
        respx.get("http://localhost:38000/tenants/by-shortname/rademo1").mock(
            return_value=httpx.Response(200, json=SAMPLE_TENANT)
        )
        respx.get("http://localhost:38000/health").mock(
            return_value=httpx.Response(200, json=SAMPLE_HEALTH)
        )
        with MimirSyncClient(tenant="rademo1") as client:
            client.health()
            assert client.tenant_id == 1
            assert client._client.headers["X-Tenant-ID"] == "1"

    @respx.mock
    def test_second_request_reuses_cached_integer(self):
        resolve_route = respx.get("http://localhost:38000/tenants/by-shortname/rademo1").mock(
            return_value=httpx.Response(200, json=SAMPLE_TENANT)
        )
        respx.get("http://localhost:38000/health").mock(
            return_value=httpx.Response(200, json=SAMPLE_HEALTH)
        )
        with MimirSyncClient(tenant="rademo1") as client:
            client.health()
            client.health()
            # Resolution endpoint called only once
            assert resolve_route.call_count == 1

    @respx.mock
    def test_unknown_shortname_raises_tenant_error(self):
        respx.get("http://localhost:38000/tenants/by-shortname/nonexistent").mock(
            return_value=httpx.Response(404, json={"detail": "Not found"})
        )
        respx.get("http://localhost:38000/health").mock(
            return_value=httpx.Response(200, json=SAMPLE_HEALTH)
        )
        with MimirSyncClient(tenant="nonexistent") as client, pytest.raises(MimirTenantError, match="not found"):
            client.health()

    @respx.mock
    def test_no_resolution_when_no_tenant_set(self):
        """System-level calls work without tenant set (State A)."""
        resolve_route = respx.get(url__regex=r".*/tenants/by-shortname/.*").mock(
            return_value=httpx.Response(200, json=SAMPLE_TENANT)
        )
        respx.get("http://localhost:38000/health").mock(
            return_value=httpx.Response(200, json=SAMPLE_HEALTH)
        )
        with MimirSyncClient() as client:
            h = client.health()
            assert h.status == "healthy"
            assert resolve_route.call_count == 0

    @respx.mock
    def test_no_resolution_when_tenant_id_set_directly(self):
        """Deprecated path skips resolution entirely."""
        resolve_route = respx.get(url__regex=r".*/tenants/by-shortname/.*").mock(
            return_value=httpx.Response(200, json=SAMPLE_TENANT)
        )
        respx.get("http://localhost:38000/health").mock(
            return_value=httpx.Response(200, json=SAMPLE_HEALTH)
        )
        with pytest.warns(DeprecationWarning):
            client = MimirSyncClient(tenant_id=1)
        with client:
            client.health()
            assert resolve_route.call_count == 0


# --- Context Manager ---


class TestSyncContextManager:
    def test_context_manager(self):
        with MimirSyncClient(tenant="dev") as client:
            assert client.tenant == "dev"

    def test_is_closed_after_exit(self):
        client = MimirSyncClient(tenant="dev")
        with client:
            pass
        assert client._client.is_closed


# --- Error Mapping ---


class TestSyncErrorMapping:
    @respx.mock
    def test_404_raises_not_found(self):
        respx.get("http://localhost:38000/tenants/999").mock(
            return_value=httpx.Response(404, json={"detail": "Tenant not found"})
        )
        with pytest.warns(DeprecationWarning):
            client = MimirSyncClient(tenant_id=1)
        with client, pytest.raises(MimirNotFoundError, match="Tenant not found"):
            client.get_tenant(999)

    @respx.mock
    def test_409_raises_conflict(self):
        respx.post("http://localhost:38000/relations").mock(
            return_value=httpx.Response(409, json={"detail": "Relation already exists"})
        )
        with pytest.warns(DeprecationWarning):
            client = MimirSyncClient(tenant_id=1)
        with client, pytest.raises(MimirConflictError, match="Relation already exists"):
            client.create_relation("a" * 36, "b" * 36, "derived_from")

    @respx.mock
    def test_422_raises_validation(self):
        respx.post("http://localhost:38000/artifacts").mock(
            return_value=httpx.Response(422, json={"detail": "Validation error"})
        )
        with pytest.warns(DeprecationWarning):
            client = MimirSyncClient(tenant_id=1)
        with client, pytest.raises(MimirValidationError, match="Validation error"):
            client.create_artifact("bad_type")

    @respx.mock
    def test_500_raises_server_error(self):
        respx.get("http://localhost:38000/health").mock(
            return_value=httpx.Response(500, json={"detail": "Internal server error"})
        )
        with pytest.warns(DeprecationWarning):
            client = MimirSyncClient(tenant_id=1)
        with client, pytest.raises(MimirServerError, match="Internal server error"):
            client.health()

    @respx.mock
    def test_other_4xx_raises_mimir_error(self):
        respx.get("http://localhost:38000/tenants/1").mock(
            return_value=httpx.Response(403, json={"detail": "Forbidden"})
        )
        with pytest.warns(DeprecationWarning):
            client = MimirSyncClient(tenant_id=1)
        with client, pytest.raises(MimirError, match="HTTP 403"):
            client.get_tenant(1)


# --- Tenant Methods ---


class TestSyncTenantMethods:
    @respx.mock
    def test_create_tenant(self):
        respx.post("http://localhost:38000/tenants").mock(
            return_value=httpx.Response(201, json=SAMPLE_TENANT)
        )
        with MimirSyncClient() as client:
            tenant = client.create_tenant("dev", "Development")
            assert isinstance(tenant, Tenant)
            assert tenant.shortname == "dev"
            assert tenant.id == 1

    @respx.mock
    def test_create_tenant_minimal_response(self):
        """Server may return minimal tenant (only required fields)."""
        respx.post("http://localhost:38000/tenants").mock(
            return_value=httpx.Response(201, json=SAMPLE_TENANT_MINIMAL)
        )
        with MimirSyncClient() as client:
            tenant = client.create_tenant("test", "Test")
            assert isinstance(tenant, Tenant)
            assert tenant.shortname == "test"
            assert tenant.tenant_type == "environment"

    @respx.mock
    def test_get_tenant(self):
        respx.get("http://localhost:38000/tenants/1").mock(
            return_value=httpx.Response(200, json=SAMPLE_TENANT)
        )
        with pytest.warns(DeprecationWarning):
            client = MimirSyncClient(tenant_id=1)
        with client:
            tenant = client.get_tenant(1)
            assert isinstance(tenant, Tenant)
            assert tenant.name == "Development"

    @respx.mock
    def test_list_tenants(self):
        respx.get("http://localhost:38000/tenants").mock(
            return_value=httpx.Response(200, json={"items": [SAMPLE_TENANT], "total": 1})
        )
        with MimirSyncClient() as client:
            result = client.list_tenants()
            assert isinstance(result, TenantList)
            assert result.total == 1
            assert len(result.items) == 1

    @respx.mock
    def test_delete_tenant_returns_none(self):
        respx.delete("http://localhost:38000/tenants/1").mock(
            return_value=httpx.Response(204)
        )
        with MimirSyncClient() as client:
            result = client.delete_tenant(1)
            assert result is None

    @respx.mock
    def test_ensure_tenant_finds_existing(self):
        respx.get("http://localhost:38000/tenants/by-shortname/dev").mock(
            return_value=httpx.Response(200, json=SAMPLE_TENANT)
        )
        with MimirSyncClient() as client:
            tenant = client.ensure_tenant("dev", "Development")
            assert tenant.id == 1
            assert client.tenant == "dev"
            assert client.tenant_id == 1
            assert client._client.headers["X-Tenant-ID"] == "1"

    @respx.mock
    def test_ensure_tenant_creates_new(self):
        respx.get("http://localhost:38000/tenants/by-shortname/new").mock(
            return_value=httpx.Response(404, json={"detail": "Not found"})
        )
        new_tenant = {**SAMPLE_TENANT, "id": 2, "shortname": "new", "name": "New Tenant"}
        respx.post("http://localhost:38000/tenants").mock(
            return_value=httpx.Response(201, json=new_tenant)
        )
        with MimirSyncClient() as client:
            tenant = client.ensure_tenant("new", "New Tenant")
            assert tenant.id == 2
            assert client.tenant == "new"
            assert client.tenant_id == 2

    @respx.mock
    def test_ensure_tenant_replaces_previous(self):
        """ensure_tenant with new shortname replaces the prior tenant."""
        respx.get("http://localhost:38000/tenants/by-shortname/first").mock(
            return_value=httpx.Response(200, json=SAMPLE_TENANT)
        )
        second_tenant = {**SAMPLE_TENANT, "id": 5, "shortname": "second", "name": "Second"}
        respx.get("http://localhost:38000/tenants/by-shortname/second").mock(
            return_value=httpx.Response(200, json=second_tenant)
        )
        with MimirSyncClient() as client:
            client.ensure_tenant("first", "First")
            assert client.tenant == "first"
            client.ensure_tenant("second", "Second")
            assert client.tenant == "second"
            assert client.tenant_id == 5


# --- Artifact Methods ---


class TestSyncArtifactMethods:
    @respx.mock
    def test_create_artifact(self):
        respx.get("http://localhost:38000/tenants/by-shortname/dev").mock(
            return_value=httpx.Response(200, json=SAMPLE_TENANT)
        )
        respx.post("http://localhost:38000/artifacts").mock(
            return_value=httpx.Response(201, json=SAMPLE_ARTIFACT)
        )
        with MimirSyncClient(tenant="dev") as client:
            artifact = client.create_artifact(
                "document", title="Test Artifact", content="Test content"
            )
            assert isinstance(artifact, Artifact)
            assert artifact.title == "Test Artifact"
            assert artifact.artifact_type == "document"

    @respx.mock
    def test_list_artifacts(self):
        respx.get("http://localhost:38000/tenants/by-shortname/dev").mock(
            return_value=httpx.Response(200, json=SAMPLE_TENANT)
        )
        respx.get("http://localhost:38000/artifacts").mock(
            return_value=httpx.Response(
                200,
                json={"items": [SAMPLE_ARTIFACT], "total": 1, "limit": 50, "offset": 0},
            )
        )
        with MimirSyncClient(tenant="dev") as client:
            result = client.list_artifacts(artifact_type="document")
            assert isinstance(result, ArtifactList)
            assert result.total == 1


# --- Search Methods ---


class TestSyncSearchMethods:
    @respx.mock
    def test_search_fulltext(self):
        respx.get("http://localhost:38000/tenants/by-shortname/dev").mock(
            return_value=httpx.Response(200, json=SAMPLE_TENANT)
        )
        respx.post("http://localhost:38000/search").mock(
            return_value=httpx.Response(200, json=SAMPLE_SEARCH_RESPONSE)
        )
        with MimirSyncClient(tenant="dev") as client:
            result = client.search_fulltext("test query")
            assert isinstance(result, SearchResponse)
            assert result.strategy == "fulltext"
            assert result.query == "test query"
            assert len(result.results) == 1
            assert result.results[0].score == 0.85

    @respx.mock
    def test_unified_search(self):
        respx.get("http://localhost:38000/tenants/by-shortname/dev").mock(
            return_value=httpx.Response(200, json=SAMPLE_TENANT)
        )
        respx.post("http://localhost:38000/search").mock(
            return_value=httpx.Response(200, json=SAMPLE_SEARCH_RESPONSE)
        )
        with MimirSyncClient(tenant="dev") as client:
            result = client.search(query="test", limit=10)
            assert isinstance(result, SearchResponse)
            assert result.total == 1


# --- Health Methods ---


class TestSyncHealthMethods:
    @respx.mock
    def test_health(self):
        respx.get("http://localhost:38000/health").mock(
            return_value=httpx.Response(200, json=SAMPLE_HEALTH)
        )
        with MimirSyncClient() as client:
            h = client.health()
            assert isinstance(h, HealthResponse)
            assert h.status == "healthy"
            assert h.version == "5.0.1"

    @respx.mock
    def test_is_healthy_true(self):
        respx.get("http://localhost:38000/health").mock(
            return_value=httpx.Response(200, json=SAMPLE_HEALTH)
        )
        with MimirSyncClient() as client:
            assert client.is_healthy() is True

    @respx.mock
    def test_is_healthy_false_on_error(self):
        respx.get("http://localhost:38000/health").mock(
            return_value=httpx.Response(500, json={"detail": "down"})
        )
        with MimirSyncClient() as client:
            assert client.is_healthy() is False


# --- Header Injection ---


class TestSyncHeaderInjection:
    @respx.mock
    def test_tenant_header_sent_after_resolution(self):
        respx.get("http://localhost:38000/tenants/by-shortname/dev").mock(
            return_value=httpx.Response(200, json=SAMPLE_TENANT)
        )
        route = respx.get("http://localhost:38000/tenants/1").mock(
            return_value=httpx.Response(200, json=SAMPLE_TENANT)
        )
        with MimirSyncClient(tenant="dev") as client:
            client.get_tenant(1)
            assert route.calls[0].request.headers["X-Tenant-ID"] == "1"

    @respx.mock
    def test_no_tenant_header_when_none(self):
        route = respx.get("http://localhost:38000/tenants/1").mock(
            return_value=httpx.Response(200, json=SAMPLE_TENANT)
        )
        with MimirSyncClient(tenant_id=None) as client:
            client.get_tenant(1)
            assert "X-Tenant-ID" not in route.calls[0].request.headers

    @respx.mock
    def test_tenant_header_with_deprecated_tenant_id(self):
        route = respx.get("http://localhost:38000/tenants/1").mock(
            return_value=httpx.Response(200, json=SAMPLE_TENANT)
        )
        with pytest.warns(DeprecationWarning):
            client = MimirSyncClient(tenant_id=42)
        with client:
            client.get_tenant(1)
            assert route.calls[0].request.headers["X-Tenant-ID"] == "42"
