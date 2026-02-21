"""Unit tests for the graph engine pure functions.

Tests Cypher builders, path extraction, and relation type filtering.
All tests are pure — no database or I/O required.
"""

from uuid import UUID

from mimir.schemas.graph import (
    GraphScopeTooLargeError,
    PathResult,
    PathStep,
    TraversalResult,
)
from mimir.services.graph_engine import (
    _build_find_paths_cypher,
    _build_traverse_cypher,
    _extract_path_steps,
    _filter_paths_by_relation_types,
)

# Test UUIDs
A_ID = "00000000-0000-0000-0000-000000000001"
B_ID = "00000000-0000-0000-0000-000000000002"
C_ID = "00000000-0000-0000-0000-000000000003"
D_ID = "00000000-0000-0000-0000-000000000004"


# =============================================================================
# _build_traverse_cypher
# =============================================================================


class TestBuildTraverseCypher:
    """Test Cypher query generation for traversal."""

    def test_undirected_default(self):
        cypher = _build_traverse_cypher(A_ID, max_depth=3)
        assert f"mimir_id: '{A_ID}'" in cypher
        assert "-[*1..3]-" in cypher
        assert "->(" not in cypher
        assert "LIMIT 500" in cypher
        assert "RETURN path" in cypher

    def test_outgoing_direction(self):
        cypher = _build_traverse_cypher(A_ID, max_depth=2, direction="outgoing")
        assert "-[*1..2]->" in cypher

    def test_incoming_direction(self):
        cypher = _build_traverse_cypher(A_ID, max_depth=5, direction="incoming")
        assert "<-[*1..5]-" in cypher

    def test_custom_limit(self):
        cypher = _build_traverse_cypher(A_ID, max_depth=3, limit=100)
        assert "LIMIT 100" in cypher

    def test_depth_1(self):
        cypher = _build_traverse_cypher(A_ID, max_depth=1)
        assert "-[*1..1]-" in cypher

    def test_large_depth(self):
        cypher = _build_traverse_cypher(A_ID, max_depth=20)
        assert "-[*1..20]-" in cypher


# =============================================================================
# _build_find_paths_cypher
# =============================================================================


class TestBuildFindPathsCypher:
    """Test Cypher query generation for path finding."""

    def test_default(self):
        cypher = _build_find_paths_cypher(A_ID, B_ID, max_depth=10)
        assert f"mimir_id: '{A_ID}'" in cypher
        assert f"mimir_id: '{B_ID}'" in cypher
        assert "-[*1..10]-" in cypher
        assert "ORDER BY length(path) ASC" in cypher
        assert "LIMIT 10" in cypher

    def test_custom_limit(self):
        cypher = _build_find_paths_cypher(A_ID, B_ID, max_depth=5, limit=3)
        assert "LIMIT 3" in cypher
        assert "-[*1..5]-" in cypher


# =============================================================================
# _extract_path_steps
# =============================================================================


def _make_vertex(age_id: int, mimir_id: str) -> dict:
    """Helper to build a parsed AGE vertex dict."""
    return {
        "id": age_id,
        "label": "Artifact",
        "properties": {"mimir_id": mimir_id, "title": f"Artifact {mimir_id[:8]}"},
    }


def _make_edge(age_id: int, start_id: int, end_id: int, relation_type: str) -> dict:
    """Helper to build a parsed AGE edge dict."""
    return {
        "id": age_id,
        "label": "Relation",
        "start_id": start_id,
        "end_id": end_id,
        "properties": {"relation_type": relation_type},
    }


class TestExtractPathSteps:
    """Test path step extraction from parsed AGE path elements."""

    def test_single_hop_outgoing(self):
        """A --derived_from--> B (edge starts at A's vertex id)."""
        v_a = _make_vertex(100, A_ID)
        e_ab = _make_edge(200, 100, 101, "derived_from")
        v_b = _make_vertex(101, B_ID)

        steps = _extract_path_steps([v_a, e_ab, v_b], A_ID)

        assert len(steps) == 1
        assert steps[0].relation_type == "derived_from"
        assert steps[0].direction == "outgoing"
        assert steps[0].from_artifact_id == UUID(A_ID)
        assert steps[0].to_artifact_id == UUID(B_ID)

    def test_single_hop_incoming(self):
        """A <--supports-- B (edge starts at B's vertex id, traversal from A)."""
        v_a = _make_vertex(100, A_ID)
        e_ba = _make_edge(200, 101, 100, "supports")  # start=B, end=A
        v_b = _make_vertex(101, B_ID)

        steps = _extract_path_steps([v_a, e_ba, v_b], A_ID)

        assert len(steps) == 1
        assert steps[0].relation_type == "supports"
        assert steps[0].direction == "incoming"
        # For incoming: from=next_vertex(B), to=current_vertex(A)
        assert steps[0].from_artifact_id == UUID(B_ID)
        assert steps[0].to_artifact_id == UUID(A_ID)

    def test_two_hop_path(self):
        """A --derived_from--> B --supports--> C."""
        v_a = _make_vertex(100, A_ID)
        e_ab = _make_edge(200, 100, 101, "derived_from")
        v_b = _make_vertex(101, B_ID)
        e_bc = _make_edge(201, 101, 102, "supports")
        v_c = _make_vertex(102, C_ID)

        steps = _extract_path_steps([v_a, e_ab, v_b, e_bc, v_c], A_ID)

        assert len(steps) == 2
        assert steps[0].relation_type == "derived_from"
        assert steps[0].direction == "outgoing"
        assert steps[1].relation_type == "supports"
        assert steps[1].direction == "outgoing"
        assert steps[1].from_artifact_id == UUID(B_ID)
        assert steps[1].to_artifact_id == UUID(C_ID)

    def test_three_hop_path(self):
        """A -> B -> C -> D."""
        v_a = _make_vertex(100, A_ID)
        e_ab = _make_edge(200, 100, 101, "derived_from")
        v_b = _make_vertex(101, B_ID)
        e_bc = _make_edge(201, 101, 102, "supports")
        v_c = _make_vertex(102, C_ID)
        e_cd = _make_edge(202, 102, 103, "references")
        v_d = _make_vertex(103, D_ID)

        steps = _extract_path_steps([v_a, e_ab, v_b, e_bc, v_c, e_cd, v_d], A_ID)

        assert len(steps) == 3
        assert [s.relation_type for s in steps] == [
            "derived_from",
            "supports",
            "references",
        ]

    def test_empty_path(self):
        steps = _extract_path_steps([], A_ID)
        assert steps == []

    def test_single_vertex_no_edges(self):
        v_a = _make_vertex(100, A_ID)
        steps = _extract_path_steps([v_a], A_ID)
        assert steps == []


# =============================================================================
# _filter_paths_by_relation_types
# =============================================================================


class TestFilterPathsByRelationTypes:
    """Test Python-side relation type filtering."""

    def _make_path_with_steps(self, relation_types: list[str]):
        """Create a (path_elements, steps) tuple with given types."""
        steps = [
            PathStep(
                relation_type=rt,
                direction="outgoing",
                from_artifact_id=UUID(A_ID),
                to_artifact_id=UUID(B_ID),
            )
            for rt in relation_types
        ]
        return ([], steps)  # Empty elements, we only filter on steps

    def test_all_edges_match(self):
        paths = [self._make_path_with_steps(["derived_from", "derived_from"])]
        result = _filter_paths_by_relation_types(paths, ["derived_from"])
        assert len(result) == 1

    def test_some_edges_dont_match(self):
        paths = [self._make_path_with_steps(["derived_from", "supports"])]
        result = _filter_paths_by_relation_types(paths, ["derived_from"])
        assert len(result) == 0

    def test_multiple_allowed_types(self):
        paths = [self._make_path_with_steps(["derived_from", "supports"])]
        result = _filter_paths_by_relation_types(paths, ["derived_from", "supports"])
        assert len(result) == 1

    def test_filters_some_paths(self):
        paths = [
            self._make_path_with_steps(["derived_from"]),
            self._make_path_with_steps(["supports"]),
            self._make_path_with_steps(["derived_from", "supports"]),
        ]
        result = _filter_paths_by_relation_types(paths, ["derived_from"])
        assert len(result) == 1  # Only first path

    def test_empty_paths_list(self):
        result = _filter_paths_by_relation_types([], ["derived_from"])
        assert result == []

    def test_empty_steps_match_all(self):
        """Path with zero steps should pass (vacuously true)."""
        paths = [([], [])]
        result = _filter_paths_by_relation_types(paths, ["derived_from"])
        assert len(result) == 1


# =============================================================================
# Domain Types
# =============================================================================


class TestTraversalResult:
    """Test TraversalResult dataclass construction."""

    def test_basic_construction(self):
        result = TraversalResult(
            artifact_id=UUID(A_ID),
            depth=2,
            relation_path=[
                PathStep(
                    relation_type="derived_from",
                    direction="outgoing",
                    from_artifact_id=UUID(A_ID),
                    to_artifact_id=UUID(B_ID),
                ),
                PathStep(
                    relation_type="supports",
                    direction="outgoing",
                    from_artifact_id=UUID(B_ID),
                    to_artifact_id=UUID(C_ID),
                ),
            ],
        )
        assert result.artifact_id == UUID(A_ID)
        assert result.depth == 2
        assert len(result.relation_path) == 2

    def test_start_vertex_depth_zero(self):
        result = TraversalResult(
            artifact_id=UUID(A_ID),
            depth=0,
            relation_path=[],
        )
        assert result.depth == 0
        assert result.relation_path == []


class TestPathResult:
    """Test PathResult dataclass construction."""

    def test_basic_construction(self):
        steps = [
            PathStep(
                relation_type="derived_from",
                direction="outgoing",
                from_artifact_id=UUID(A_ID),
                to_artifact_id=UUID(B_ID),
            ),
        ]
        result = PathResult(
            steps=steps,
            length=1,
            start_artifact_id=UUID(A_ID),
            end_artifact_id=UUID(B_ID),
        )
        assert result.length == 1
        assert result.start_artifact_id == UUID(A_ID)


class TestGraphScopeTooLargeError:
    """Test exception attributes."""

    def test_message_and_attrs(self):
        exc = GraphScopeTooLargeError(count=600, limit=500)
        assert exc.count == 600
        assert exc.limit == 500
        assert "600" in str(exc)
        assert "500" in str(exc)
