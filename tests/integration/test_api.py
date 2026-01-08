"""
Integration tests for the Mímir API.

These tests run against a live database via the running API.
Requires: docker compose up

Focus: Test actual behavior, not just that endpoints respond.
"""

from uuid import uuid4

import pytest


@pytest.mark.integration
class TestTenantAPI:
    """Integration tests for tenant CRUD operations."""

    @pytest.mark.asyncio
    async def test_create_tenant_persists(self, async_client):
        """Creating a tenant should persist it to the database."""
        unique_name = f"test-{uuid4().hex[:8]}"
        response = await async_client.post(
            "/tenants",
            json={
                "shortname": unique_name,
                "name": "Integration Test Tenant",
                "tenant_type": "experiment",
            },
        )
        assert response.status_code == 201, response.text

        data = response.json()
        tenant_id = data["id"]

        # Verify it can be retrieved
        get_response = await async_client.get(f"/tenants/{tenant_id}")
        assert get_response.status_code == 200
        assert get_response.json()["shortname"] == unique_name

    @pytest.mark.asyncio
    async def test_duplicate_shortname_rejected(self, async_client):
        """Database should reject duplicate shortnames."""
        unique_name = f"dup-{uuid4().hex[:8]}"

        # Create first tenant
        response1 = await async_client.post(
            "/tenants",
            json={"shortname": unique_name, "name": "First", "tenant_type": "environment"},
        )
        assert response1.status_code == 201

        # Attempt duplicate should fail
        response2 = await async_client.post(
            "/tenants",
            json={"shortname": unique_name, "name": "Second", "tenant_type": "environment"},
        )
        # Should be 409 Conflict or 400 Bad Request depending on implementation
        assert response2.status_code in [400, 409, 500], f"Expected error, got {response2.status_code}"

    @pytest.mark.asyncio
    async def test_invalid_tenant_type_rejected(self, async_client):
        """API should reject invalid tenant types."""
        response = await async_client.post(
            "/tenants",
            json={"shortname": "test", "name": "Test", "tenant_type": "invalid_type"},
        )
        assert response.status_code == 422  # Pydantic validation error


@pytest.mark.integration
class TestArtifactAPI:
    """Integration tests for artifact CRUD operations."""

    @pytest.fixture
    async def test_tenant(self, async_client):
        """Create a tenant for artifact tests."""
        unique_name = f"art-{uuid4().hex[:8]}"
        response = await async_client.post(
            "/tenants",
            json={"shortname": unique_name, "name": "Artifact Test", "tenant_type": "experiment"},
        )
        return response.json()

    @pytest.mark.asyncio
    async def test_create_artifact_requires_tenant_header(self, async_client):
        """Creating artifact without X-Tenant-ID should fail."""
        response = await async_client.post(
            "/artifacts",
            json={"artifact_type": "document", "title": "Test"},
        )
        # Should be 400 or 422 for missing header
        assert response.status_code in [400, 422], response.text

    @pytest.mark.asyncio
    async def test_create_artifact_validates_type(self, async_client, test_tenant):
        """Creating artifact with invalid type should fail at database."""
        response = await async_client.post(
            "/artifacts",
            headers={"X-Tenant-ID": str(test_tenant["id"])},
            json={"artifact_type": "nonexistent_type", "title": "Test"},
        )
        # Should fail due to FK constraint
        assert response.status_code in [400, 422, 500], response.text

    @pytest.mark.asyncio
    async def test_artifact_crud_lifecycle(self, async_client, test_tenant):
        """Full CRUD lifecycle for artifacts."""
        tenant_id = str(test_tenant["id"])
        headers = {"X-Tenant-ID": tenant_id}

        # Create
        create_response = await async_client.post(
            "/artifacts",
            headers=headers,
            json={
                "artifact_type": "document",
                "title": "Test Document",
                "content": "This is test content",
                "metadata": {"source": "integration_test"},
            },
        )
        assert create_response.status_code == 201, create_response.text
        artifact = create_response.json()
        artifact_id = artifact["id"]

        # Read
        get_response = await async_client.get(f"/artifacts/{artifact_id}", headers=headers)
        assert get_response.status_code == 200
        assert get_response.json()["title"] == "Test Document"

        # Update
        update_response = await async_client.patch(
            f"/artifacts/{artifact_id}",
            headers=headers,
            json={"title": "Updated Title"},
        )
        assert update_response.status_code == 200
        assert update_response.json()["title"] == "Updated Title"

        # Delete
        delete_response = await async_client.delete(f"/artifacts/{artifact_id}", headers=headers)
        assert delete_response.status_code in [200, 204]

        # Verify deleted
        verify_response = await async_client.get(f"/artifacts/{artifact_id}", headers=headers)
        assert verify_response.status_code == 404


@pytest.mark.integration
class TestRelationAPI:
    """Integration tests for relation operations."""

    @pytest.fixture
    async def test_artifacts(self, async_client):
        """Create tenant and two artifacts for relation tests."""
        # Create tenant
        tenant_resp = await async_client.post(
            "/tenants",
            json={"shortname": f"rel-{uuid4().hex[:8]}", "name": "Relation Test", "tenant_type": "experiment"},
        )
        tenant = tenant_resp.json()
        headers = {"X-Tenant-ID": str(tenant["id"])}

        # Create two artifacts
        art1_resp = await async_client.post(
            "/artifacts",
            headers=headers,
            json={"artifact_type": "document", "title": "Source Doc"},
        )
        art2_resp = await async_client.post(
            "/artifacts",
            headers=headers,
            json={"artifact_type": "document", "title": "Target Doc"},
        )

        return {
            "tenant": tenant,
            "artifact1": art1_resp.json(),
            "artifact2": art2_resp.json(),
            "headers": headers,
        }

    @pytest.mark.asyncio
    async def test_create_relation_between_artifacts(self, async_client, test_artifacts):
        """Creating a relation should link two artifacts."""
        headers = test_artifacts["headers"]
        art1 = test_artifacts["artifact1"]
        art2 = test_artifacts["artifact2"]

        response = await async_client.post(
            "/relations",
            headers=headers,
            json={
                "source_type": "artifact",
                "source_id": art1["id"],
                "target_type": "artifact",
                "target_id": art2["id"],
                "relation_type": "references",
            },
        )
        assert response.status_code == 201, response.text

        relation = response.json()
        assert relation["source_id"] == art1["id"]
        assert relation["target_id"] == art2["id"]

    @pytest.mark.asyncio
    async def test_invalid_relation_type_rejected(self, async_client, test_artifacts):
        """Invalid relation type should be rejected (FK constraint)."""
        headers = test_artifacts["headers"]
        art1 = test_artifacts["artifact1"]
        art2 = test_artifacts["artifact2"]

        response = await async_client.post(
            "/relations",
            headers=headers,
            json={
                "source_type": "artifact",
                "source_id": art1["id"],
                "target_type": "artifact",
                "target_id": art2["id"],
                "relation_type": "nonexistent_relation",
            },
        )
        # Should fail due to FK constraint
        assert response.status_code in [400, 422, 500], response.text


@pytest.mark.integration
class TestProvenanceAPI:
    """Integration tests for provenance tracking."""

    @pytest.mark.asyncio
    async def test_artifact_creation_creates_provenance(self, async_client):
        """Creating an artifact should automatically create a provenance event."""
        # Create tenant
        tenant_resp = await async_client.post(
            "/tenants",
            json={"shortname": f"prov-{uuid4().hex[:8]}", "name": "Provenance Test", "tenant_type": "experiment"},
        )
        tenant = tenant_resp.json()
        headers = {"X-Tenant-ID": str(tenant["id"])}

        # Create artifact
        art_resp = await async_client.post(
            "/artifacts",
            headers=headers,
            json={"artifact_type": "note", "title": "Provenance Test Note"},
        )
        assert art_resp.status_code == 201
        artifact = art_resp.json()

        # Check provenance was recorded
        prov_resp = await async_client.get(
            f"/provenance/entity/artifact/{artifact['id']}",
            headers=headers,
        )
        assert prov_resp.status_code == 200
        events = prov_resp.json()

        # Should have at least one 'create' event
        assert len(events) > 0
        create_events = [e for e in events if e.get("action") == "create"]
        assert len(create_events) >= 1, f"Expected create event, got: {events}"


@pytest.mark.integration
class TestSearchAPI:
    """Integration tests for search functionality."""

    @pytest.mark.asyncio
    async def test_fulltext_search_returns_matches(self, async_client):
        """Full-text search should return matching artifacts."""
        # Create tenant
        tenant_resp = await async_client.post(
            "/tenants",
            json={"shortname": f"search-{uuid4().hex[:8]}", "name": "Search Test", "tenant_type": "experiment"},
        )
        tenant = tenant_resp.json()
        headers = {"X-Tenant-ID": str(tenant["id"])}

        # Create artifact with specific content
        unique_word = f"uniqueword{uuid4().hex[:8]}"
        await async_client.post(
            "/artifacts",
            headers=headers,
            json={
                "artifact_type": "document",
                "title": f"Document with {unique_word}",
                "content": f"This document contains the {unique_word} for testing.",
            },
        )

        # Search for that unique word (GET with query params)
        search_resp = await async_client.get(
            "/search/fulltext",
            headers=headers,
            params={"query": unique_word, "limit": 10},
        )
        assert search_resp.status_code == 200
        results = search_resp.json()

        # Should find our document - results has 'items' list
        assert results.get("total", 0) > 0 or len(results.get("items", [])) > 0, f"Expected to find document with '{unique_word}', got: {results}"
