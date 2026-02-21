"""Integration tests for the Graph Traversal Engine.

Requires a running PostgreSQL + AGE instance (docker compose up).
Creates a known graph topology via the API, then exercises traverse()
and find_paths() against the live AGE graph.

Test Graph Topology (§10 of technical design):

    A ──derived_from──▶ B ──supports──▶ C ──derived_from──▶ D
    │                                   │
    └──────references────▶ E            └──supports──▶ F

6 artifacts (A-F), 5 relations.
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient
from uuid import UUID

from mimir.services import graph_engine
from mimir.schemas.graph import (
    GraphScopeTooLargeError,
    TraversalResult,
    PathResult,
)


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
async def test_graph(async_client: AsyncClient):
    """Create a test tenant with 6 artifacts and 5 relations forming the known topology.

    Returns a dict with tenant_id and artifact UUIDs keyed A-F.
    """
    # Create tenant
    resp = await async_client.post("/tenants", json={
        "shortname": "graph-test",
        "name": "Graph Traversal Test Tenant",
        "tenant_type": "environment",
    })
    # If tenant already exists, try to find it
    if resp.status_code == 409:
        resp = await async_client.get("/tenants")
        tenants = resp.json()
        tenant_id = next(
            t["id"] for t in tenants
            if t["shortname"] == "graph-test"
        )
    else:
        assert resp.status_code == 201, f"Create tenant failed: {resp.text}"
        tenant_id = resp.json()["id"]

    headers = {"X-Tenant-ID": str(tenant_id)}

    # Create 6 artifacts (A-F)
    artifact_ids = {}
    for label in ["A", "B", "C", "D", "E", "F"]:
        resp = await async_client.post("/artifacts", json={
            "artifact_type": "document",
            "title": f"Artifact {label}",
            "content": f"Content for artifact {label}",
            "source": "graph-test",
        }, headers=headers)
        assert resp.status_code == 201, f"Create artifact {label} failed: {resp.text}"
        artifact_ids[label] = UUID(resp.json()["id"])

    # Create 5 relations forming the test topology:
    # A --derived_from--> B
    # B --supports--> C
    # C --derived_from--> D
    # A --references--> E
    # C --supports--> F
    relations = [
        (artifact_ids["A"], artifact_ids["B"], "derived_from"),
        (artifact_ids["B"], artifact_ids["C"], "supports"),
        (artifact_ids["C"], artifact_ids["D"], "derived_from"),
        (artifact_ids["A"], artifact_ids["E"], "references"),
        (artifact_ids["C"], artifact_ids["F"], "supports"),
    ]

    for source_id, target_id, rel_type in relations:
        resp = await async_client.post("/relations", json={
            "source_id": str(source_id),
            "target_id": str(target_id),
            "relation_type": rel_type,
        }, headers=headers)
        assert resp.status_code in (201, 409), f"Create relation failed: {resp.text}"

    return {
        "tenant_id": tenant_id,
        **artifact_ids,
    }


# =============================================================================
# Traverse Tests
# =============================================================================


@pytest.mark.asyncio
class TestTraverse:
    """Test graph_engine.traverse() against live AGE graph."""

    async def test_traverse_depth_1(self, test_graph):
        """From A, depth=1 → {B, E} (+ A if include_start)."""
        results = await graph_engine.traverse(
            tenant_id=test_graph["tenant_id"],
            start_artifact_id=test_graph["A"],
            max_depth=1,
            include_start=True,
        )

        result_ids = {r.artifact_id for r in results}
        assert test_graph["A"] in result_ids, "Start artifact A should be included"
        assert test_graph["B"] in result_ids, "B is 1 hop from A via derived_from"
        assert test_graph["E"] in result_ids, "E is 1 hop from A via references"
        # C, D, F should NOT be at depth 1
        assert test_graph["C"] not in result_ids
        assert test_graph["D"] not in result_ids

    async def test_traverse_depth_2(self, test_graph):
        """From A, depth=2 → {B, C, E} (+ A)."""
        results = await graph_engine.traverse(
            tenant_id=test_graph["tenant_id"],
            start_artifact_id=test_graph["A"],
            max_depth=2,
            include_start=True,
        )

        result_ids = {r.artifact_id for r in results}
        assert test_graph["A"] in result_ids
        assert test_graph["B"] in result_ids
        assert test_graph["C"] in result_ids, "C is 2 hops from A (A→B→C)"
        assert test_graph["E"] in result_ids
        # D and F are at depth 3
        assert test_graph["D"] not in result_ids
        assert test_graph["F"] not in result_ids

    async def test_traverse_full_depth(self, test_graph):
        """From A, depth=10 → all artifacts {B, C, D, E, F} (+ A)."""
        results = await graph_engine.traverse(
            tenant_id=test_graph["tenant_id"],
            start_artifact_id=test_graph["A"],
            max_depth=10,
            include_start=True,
        )

        result_ids = {r.artifact_id for r in results}
        for label in ["A", "B", "C", "D", "E", "F"]:
            assert test_graph[label] in result_ids, f"{label} should be reachable"

    async def test_traverse_with_relation_filter(self, test_graph):
        """From A, relation_types=["derived_from"], depth=1 → {B} only."""
        results = await graph_engine.traverse(
            tenant_id=test_graph["tenant_id"],
            start_artifact_id=test_graph["A"],
            max_depth=1,
            relation_types=["derived_from"],
            include_start=False,
        )

        result_ids = {r.artifact_id for r in results}
        assert test_graph["B"] in result_ids, "B is connected to A via derived_from"
        assert test_graph["E"] not in result_ids, "E is connected via references, not derived_from"

    async def test_traverse_direction_outgoing(self, test_graph):
        """From C, outgoing only → {D, F}."""
        results = await graph_engine.traverse(
            tenant_id=test_graph["tenant_id"],
            start_artifact_id=test_graph["C"],
            max_depth=10,
            direction="outgoing",
            include_start=False,
        )

        result_ids = {r.artifact_id for r in results}
        assert test_graph["D"] in result_ids, "D is outgoing from C (derived_from)"
        assert test_graph["F"] in result_ids, "F is outgoing from C (supports)"
        # B is incoming to C, should not be found with outgoing direction
        assert test_graph["B"] not in result_ids

    async def test_traverse_direction_undirected(self, test_graph):
        """From C, undirected → reaches back through incoming edges."""
        results = await graph_engine.traverse(
            tenant_id=test_graph["tenant_id"],
            start_artifact_id=test_graph["C"],
            max_depth=10,
            direction="both",
            include_start=False,
        )

        result_ids = {r.artifact_id for r in results}
        # Should reach back through B to A and E
        assert test_graph["B"] in result_ids, "B connects to C (incoming supports)"
        assert test_graph["D"] in result_ids, "D is outgoing from C"
        assert test_graph["F"] in result_ids, "F is outgoing from C"

    async def test_traverse_include_start_false(self, test_graph):
        """include_start=False should exclude the start artifact."""
        results = await graph_engine.traverse(
            tenant_id=test_graph["tenant_id"],
            start_artifact_id=test_graph["A"],
            max_depth=1,
            include_start=False,
        )

        result_ids = {r.artifact_id for r in results}
        assert test_graph["A"] not in result_ids

    async def test_traverse_sorted_by_depth(self, test_graph):
        """Results should be sorted by depth ascending."""
        results = await graph_engine.traverse(
            tenant_id=test_graph["tenant_id"],
            start_artifact_id=test_graph["A"],
            max_depth=10,
            include_start=True,
        )

        depths = [r.depth for r in results]
        assert depths == sorted(depths), f"Depths not sorted: {depths}"

    async def test_relation_path_data(self, test_graph):
        """Verify TraversalResult contains correct relation_path with types and directions."""
        results = await graph_engine.traverse(
            tenant_id=test_graph["tenant_id"],
            start_artifact_id=test_graph["A"],
            max_depth=2,
            include_start=False,
        )

        # Find result for B (1-hop from A via derived_from)
        b_result = next(
            (r for r in results if r.artifact_id == test_graph["B"]),
            None,
        )
        assert b_result is not None, "B should be in results"
        assert b_result.depth == 1
        assert len(b_result.relation_path) == 1
        assert b_result.relation_path[0].relation_type == "derived_from"

        # Find result for C (2-hops from A: A→B→C)
        c_result = next(
            (r for r in results if r.artifact_id == test_graph["C"]),
            None,
        )
        assert c_result is not None, "C should be in results"
        assert c_result.depth == 2
        assert len(c_result.relation_path) == 2


# =============================================================================
# Find Paths Tests
# =============================================================================


@pytest.mark.asyncio
class TestFindPaths:
    """Test graph_engine.find_paths() against live AGE graph."""

    async def test_find_paths_a_to_d(self, test_graph):
        """A→D: path = A→B→C→D (length 3)."""
        paths = await graph_engine.find_paths(
            tenant_id=test_graph["tenant_id"],
            from_artifact_id=test_graph["A"],
            to_artifact_id=test_graph["D"],
            max_depth=10,
        )

        assert len(paths) >= 1, "Should find at least one path A→D"
        shortest = paths[0]
        assert shortest.length == 3, f"Shortest A→D should be 3 hops, got {shortest.length}"
        assert shortest.start_artifact_id == test_graph["A"]
        assert shortest.end_artifact_id == test_graph["D"]

    async def test_find_paths_shortest_first(self, test_graph):
        """Paths should be returned shortest-first."""
        paths = await graph_engine.find_paths(
            tenant_id=test_graph["tenant_id"],
            from_artifact_id=test_graph["A"],
            to_artifact_id=test_graph["D"],
            max_depth=10,
        )

        if len(paths) > 1:
            lengths = [p.length for p in paths]
            assert lengths == sorted(lengths), f"Paths not shortest-first: {lengths}"

    async def test_find_paths_no_path(self, test_graph):
        """Between disconnected artifacts with max_depth=0 → empty."""
        # E is only connected to A. With depth=1 from E to D, no path.
        paths = await graph_engine.find_paths(
            tenant_id=test_graph["tenant_id"],
            from_artifact_id=test_graph["E"],
            to_artifact_id=test_graph["D"],
            max_depth=1,
        )

        # E→D requires at least 3 hops (E←A→B→C→D is 4 hops undirected)
        # With max_depth=1, no path should exist
        assert len(paths) == 0, f"Expected no paths with depth 1, got {len(paths)}"

    async def test_find_paths_a_to_e(self, test_graph):
        """A→E: direct path (length 1) via references."""
        paths = await graph_engine.find_paths(
            tenant_id=test_graph["tenant_id"],
            from_artifact_id=test_graph["A"],
            to_artifact_id=test_graph["E"],
            max_depth=5,
        )

        assert len(paths) >= 1
        shortest = paths[0]
        assert shortest.length == 1, "A→E should be 1 hop"


# =============================================================================
# Special Character Tests — Single-Quote / Apostrophe in Titles
# =============================================================================


@pytest.mark.asyncio
class TestSpecialCharacterTitles:
    """Verify that artifact titles containing apostrophes and backslashes
    survive the INSERT trigger (trg_artifact_create_vertex) without error.

    The trigger builds a Cypher CREATE statement with the title interpolated
    as a string literal. Before the fix, titles with single quotes caused a
    syntax error (500) because quote_literal() emitted PostgreSQL E'…' syntax
    inside $cypher$ blocks.

    These tests verify creation succeeds (201) through the API, which proves
    the trigger executed without error and the graph vertex was created.
    """

    @pytest_asyncio.fixture
    async def apostrophe_tenant(self, async_client: AsyncClient):
        """Create a dedicated tenant for special-character tests."""
        import uuid as _uuid
        shortname = f"apos-{_uuid.uuid4().hex[:8]}"
        resp = await async_client.post("/tenants", json={
            "shortname": shortname,
            "name": "Apostrophe Test Tenant",
            "tenant_type": "experiment",
        })
        assert resp.status_code == 201, f"Create tenant failed: {resp.text}"
        tenant_id = resp.json()["id"]
        return {"tenant_id": tenant_id, "headers": {"X-Tenant-ID": str(tenant_id)}}

    async def test_apostrophe_in_title(self, async_client, apostrophe_tenant):
        """Title with a single apostrophe: "What's Next"."""
        resp = await async_client.post("/artifacts", json={
            "artifact_type": "document",
            "title": "What's Next",
            "content": "Content with apostrophe",
            "source": "apostrophe-test",
        }, headers=apostrophe_tenant["headers"])
        assert resp.status_code == 201, (
            f"Artifact with apostrophe title failed: {resp.text}"
        )

    async def test_double_apostrophe_in_title(self, async_client, apostrophe_tenant):
        """Title with multiple apostrophes: "It's John's Plan"."""
        resp = await async_client.post("/artifacts", json={
            "artifact_type": "document",
            "title": "It's John's Plan",
            "content": "Content with double apostrophe",
            "source": "apostrophe-test",
        }, headers=apostrophe_tenant["headers"])
        assert resp.status_code == 201, (
            f"Artifact with double apostrophe title failed: {resp.text}"
        )

    async def test_backslash_in_title(self, async_client, apostrophe_tenant):
        """Title with backslashes: "path\\to\\file"."""
        resp = await async_client.post("/artifacts", json={
            "artifact_type": "document",
            "title": "path\\to\\file",
            "content": "Content with backslashes",
            "source": "apostrophe-test",
        }, headers=apostrophe_tenant["headers"])
        assert resp.status_code == 201, (
            f"Artifact with backslash title failed: {resp.text}"
        )

    async def test_mixed_special_chars_in_title(self, async_client, apostrophe_tenant):
        """Title with both apostrophes and backslashes: "O'Brien's C:\\Users\\doc"."""
        resp = await async_client.post("/artifacts", json={
            "artifact_type": "document",
            "title": "O'Brien's C:\\Users\\doc",
            "content": "Content with mixed specials",
            "source": "apostrophe-test",
        }, headers=apostrophe_tenant["headers"])
        assert resp.status_code == 201, (
            f"Artifact with mixed special chars title failed: {resp.text}"
        )

    async def test_relation_between_apostrophe_artifacts(self, async_client, apostrophe_tenant):
        """Create two artifacts with apostrophes, then a relation between them."""
        headers = apostrophe_tenant["headers"]

        resp1 = await async_client.post("/artifacts", json={
            "artifact_type": "document",
            "title": "What's the Problem?",
            "content": "Source artifact",
            "source": "apostrophe-test",
        }, headers=headers)
        assert resp1.status_code == 201, f"Source artifact failed: {resp1.text}"

        resp2 = await async_client.post("/artifacts", json={
            "artifact_type": "document",
            "title": "Here's the Solution",
            "content": "Target artifact",
            "source": "apostrophe-test",
        }, headers=headers)
        assert resp2.status_code == 201, f"Target artifact failed: {resp2.text}"

        resp3 = await async_client.post("/relations", json={
            "source_id": resp1.json()["id"],
            "target_id": resp2.json()["id"],
            "relation_type": "derived_from",
        }, headers=headers)
        assert resp3.status_code == 201, f"Relation creation failed: {resp3.text}"


# =============================================================================
# Error Handling Tests
# =============================================================================


@pytest.mark.asyncio
class TestGraphEngineErrors:
    """Test error handling in graph engine."""

    async def test_traverse_result_set_limit(self, test_graph):
        """Verify GraphScopeTooLargeError with artificially low limit."""
        from unittest.mock import patch

        # Patch settings to have a very low result set limit
        with patch(
            "mimir.services.graph_engine.get_settings"
        ) as mock_settings:
            mock_settings.return_value.graph_max_depth = 10
            mock_settings.return_value.graph_max_result_set = 1  # Only 1 allowed
            mock_settings.return_value.graph_query_timeout_seconds = 5

            with pytest.raises(GraphScopeTooLargeError):
                await graph_engine.traverse(
                    tenant_id=test_graph["tenant_id"],
                    start_artifact_id=test_graph["A"],
                    max_depth=10,
                    include_start=True,
                )