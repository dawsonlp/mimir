"""Integration tests for graph-scoped search.

Requires a running Mimir API at localhost:38000 (docker compose up).
Tests the graph_scope parameter in POST /search and backward compatibility
of scope_artifact_id via graph engine delegation.
"""

from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient

# =============================================================================
# Fixtures
# =============================================================================


@pytest_asyncio.fixture
async def async_client() -> AsyncClient:
    """HTTP client pointing at running API."""
    async with AsyncClient(
        base_url="http://localhost:38000",
        timeout=30.0,
    ) as client:
        yield client


@pytest_asyncio.fixture
async def search_graph(async_client: AsyncClient):
    """Create a test tenant with artifacts and relations for search testing.

    Topology:
        Root ──derived_from──▶ DocA ──supports──▶ DocB
          │
          └──references──▶ DocC

    All artifacts have searchable content containing "knowledge graph test".
    """
    # Create tenant with unique shortname to avoid collisions across runs
    unique = uuid4().hex[:8]
    resp = await async_client.post(
        "/tenants",
        json={
            "shortname": f"sg-{unique}",
            "name": "Search Graph Test Tenant",
            "tenant_type": "environment",
        },
    )
    assert resp.status_code == 201, f"Create tenant failed: {resp.text}"
    tenant_id = resp.json()["id"]

    headers = {"X-Tenant-ID": str(tenant_id)}

    # Create artifacts with searchable content
    artifacts = {}
    for label, content in [
        ("Root", "knowledge graph test root artifact for search validation"),
        ("DocA", "knowledge graph test document alpha derived content"),
        ("DocB", "knowledge graph test document beta supporting evidence"),
        ("DocC", "knowledge graph test document charlie referenced material"),
    ]:
        resp = await async_client.post(
            "/artifacts",
            json={
                "artifact_type": "document",
                "title": f"Search {label}",
                "content": content,
                "source": "search-graph-test",
            },
            headers=headers,
        )
        assert resp.status_code == 201, f"Create artifact {label} failed: {resp.text}"
        artifacts[label] = UUID(resp.json()["id"])

    # Create relations
    relations = [
        (artifacts["Root"], artifacts["DocA"], "derived_from"),
        (artifacts["DocA"], artifacts["DocB"], "supports"),
        (artifacts["Root"], artifacts["DocC"], "references"),
    ]

    for source_id, target_id, rel_type in relations:
        resp = await async_client.post(
            "/relations",
            json={
                "source_id": str(source_id),
                "target_id": str(target_id),
                "relation_type": rel_type,
            },
            headers=headers,
        )
        assert resp.status_code in (201, 409), f"Create relation failed: {resp.text}"

    return {
        "tenant_id": tenant_id,
        "headers": headers,
        **artifacts,
    }


# =============================================================================
# Graph-Scoped Search Tests
# =============================================================================


@pytest.mark.asyncio
class TestGraphScopedSearch:
    """Test graph_scope parameter in POST /search."""

    async def test_graph_scope_fulltext(self, async_client: AsyncClient, search_graph):
        """graph_scope with text search should restrict results to graph neighbors."""
        resp = await async_client.post(
            "/search",
            json={
                "query": "knowledge graph test",
                "graph_scope": {
                    "root_artifact_id": str(search_graph["Root"]),
                    "max_depth": 1,
                },
            },
            headers=search_graph["headers"],
        )

        assert resp.status_code == 200, f"Search failed: {resp.text}"
        data = resp.json()

        # With depth 1 from Root: should include Root, DocA, DocC
        # DocB is at depth 2 (Root→DocA→DocB) so should NOT be included
        result_ids = {r["artifact"]["id"] for r in data["results"]}
        assert str(search_graph["Root"]) in result_ids, "Root should be in graph scope"
        assert str(search_graph["DocA"]) in result_ids, "DocA is 1-hop from Root"
        assert str(search_graph["DocC"]) in result_ids, "DocC is 1-hop from Root"

    async def test_graph_scope_deeper_depth(
        self, async_client: AsyncClient, search_graph
    ):
        """graph_scope with depth=2 should include DocB."""
        resp = await async_client.post(
            "/search",
            json={
                "query": "knowledge graph test",
                "graph_scope": {
                    "root_artifact_id": str(search_graph["Root"]),
                    "max_depth": 2,
                },
            },
            headers=search_graph["headers"],
        )

        assert resp.status_code == 200
        data = resp.json()

        result_ids = {r["artifact"]["id"] for r in data["results"]}
        assert str(search_graph["DocB"]) in result_ids, "DocB should be at depth 2"

    async def test_graph_scope_with_relation_filter(
        self, async_client: AsyncClient, search_graph
    ):
        """graph_scope with relation_types filter."""
        resp = await async_client.post(
            "/search",
            json={
                "query": "knowledge graph test",
                "graph_scope": {
                    "root_artifact_id": str(search_graph["Root"]),
                    "max_depth": 1,
                    "relation_types": ["derived_from"],
                },
            },
            headers=search_graph["headers"],
        )

        assert resp.status_code == 200
        data = resp.json()

        result_ids = {r["artifact"]["id"] for r in data["results"]}
        # Only Root and DocA (derived_from), not DocC (references)
        assert str(search_graph["Root"]) in result_ids
        assert str(search_graph["DocA"]) in result_ids
        # DocC is connected via "references" which should be filtered out
        assert str(search_graph["DocC"]) not in result_ids

    async def test_graph_scope_outgoing_direction(
        self, async_client: AsyncClient, search_graph
    ):
        """graph_scope with direction=outgoing."""
        resp = await async_client.post(
            "/search",
            json={
                "query": "knowledge graph test",
                "graph_scope": {
                    "root_artifact_id": str(search_graph["Root"]),
                    "max_depth": 10,
                    "direction": "outgoing",
                },
            },
            headers=search_graph["headers"],
        )

        assert resp.status_code == 200
        data = resp.json()

        result_ids = {r["artifact"]["id"] for r in data["results"]}
        # All artifacts should be reachable via outgoing from Root
        assert str(search_graph["Root"]) in result_ids
        assert str(search_graph["DocA"]) in result_ids


# =============================================================================
# Backward Compatibility Tests
# =============================================================================


@pytest.mark.asyncio
class TestScopeArtifactIdCompat:
    """Test scope_artifact_id backward compatibility via graph engine."""

    async def test_scope_artifact_id_works(
        self, async_client: AsyncClient, search_graph
    ):
        """scope_artifact_id should still work (internally converts to graph_scope)."""
        resp = await async_client.post(
            "/search",
            json={
                "query": "knowledge graph test",
                "scope_artifact_id": str(search_graph["Root"]),
            },
            headers=search_graph["headers"],
        )

        assert resp.status_code == 200
        data = resp.json()
        # With converted depth=1, should find Root + direct neighbors
        assert data["total"] >= 1


# =============================================================================
# Validation Tests
# =============================================================================


@pytest.mark.asyncio
class TestGraphScopeValidation:
    """Test validation rules for graph_scope."""

    async def test_mutual_exclusion(self, async_client: AsyncClient, search_graph):
        """scope_artifact_id + graph_scope together should return 422."""
        resp = await async_client.post(
            "/search",
            json={
                "query": "test",
                "scope_artifact_id": str(search_graph["Root"]),
                "graph_scope": {
                    "root_artifact_id": str(search_graph["Root"]),
                    "max_depth": 1,
                },
            },
            headers=search_graph["headers"],
        )

        assert resp.status_code == 422, (
            f"Expected 422, got {resp.status_code}: {resp.text}"
        )

    async def test_graph_scope_invalid_direction(
        self, async_client: AsyncClient, search_graph
    ):
        """Invalid direction value should return 422."""
        resp = await async_client.post(
            "/search",
            json={
                "query": "test",
                "graph_scope": {
                    "root_artifact_id": str(search_graph["Root"]),
                    "direction": "sideways",
                },
            },
            headers=search_graph["headers"],
        )

        assert resp.status_code == 422

    async def test_graph_scope_invalid_depth(
        self, async_client: AsyncClient, search_graph
    ):
        """max_depth=0 should return 422."""
        resp = await async_client.post(
            "/search",
            json={
                "query": "test",
                "graph_scope": {
                    "root_artifact_id": str(search_graph["Root"]),
                    "max_depth": 0,
                },
            },
            headers=search_graph["headers"],
        )

        assert resp.status_code == 422
