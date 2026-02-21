"""Unit tests for the agtype parser.

Test data derived from the AGE 1.7.0 spike (scripts/age_cypher_spike.py).
All tests are pure — no database or I/O required.
"""

import pytest

from mimir.services.agtype_parser import parse_agtype_collection, parse_agtype_value

# =============================================================================
# parse_agtype_value — scalar types
# =============================================================================


class TestParseAgtypeValueScalars:
    """Scalar agtype values: strings, integers, floats, booleans, null."""

    def test_none_returns_none(self):
        assert parse_agtype_value(None) is None

    def test_scalar_string(self):
        # AGE returns property strings double-quoted inside the Python str
        result = parse_agtype_value('"derived_from"')
        assert result == "derived_from"

    def test_scalar_integer(self):
        result = parse_agtype_value("1")
        assert result == 1
        assert isinstance(result, int)

    def test_scalar_integer_large(self):
        result = parse_agtype_value("844424930131972")
        assert result == 844424930131972

    def test_scalar_float(self):
        result = parse_agtype_value("3.14")
        assert result == pytest.approx(3.14)
        assert isinstance(result, float)

    def test_scalar_boolean_true(self):
        result = parse_agtype_value("true")
        assert result is True

    def test_scalar_boolean_false(self):
        result = parse_agtype_value("false")
        assert result is False

    def test_non_string_passthrough(self):
        # If somehow a non-string value arrives, pass it through
        assert parse_agtype_value(42) == 42
        assert parse_agtype_value(3.14) == 3.14


# =============================================================================
# parse_agtype_value — vertex / edge
# =============================================================================


class TestParseAgtypeValueStructured:
    """Vertex and edge agtype values with ::vertex / ::edge suffixes."""

    def test_vertex(self):
        raw = (
            '{"id": 844424930131972, "label": "Artifact", '
            '"properties": {"mimir_id": "aaaa-bbbb", "title": "Test"}}::vertex'
        )
        result = parse_agtype_value(raw)
        assert isinstance(result, dict)
        assert result["id"] == 844424930131972
        assert result["label"] == "Artifact"
        assert result["properties"]["mimir_id"] == "aaaa-bbbb"

    def test_edge(self):
        raw = (
            '{"id": 1125899906842626, "label": "Relation", '
            '"end_id": 844424930131973, "start_id": 844424930131972, '
            '"properties": {"mimir_id": "cccc-dddd", "relation_type": "derived_from"}}::edge'
        )
        result = parse_agtype_value(raw)
        assert isinstance(result, dict)
        assert result["label"] == "Relation"
        assert result["properties"]["relation_type"] == "derived_from"
        assert result["start_id"] == 844424930131972
        assert result["end_id"] == 844424930131973

    def test_vertex_with_trailing_whitespace(self):
        raw = '{"id": 1, "label": "Artifact", "properties": {}}::vertex  '
        result = parse_agtype_value(raw)
        assert isinstance(result, dict)
        assert result["id"] == 1


# =============================================================================
# parse_agtype_value — errors
# =============================================================================


class TestParseAgtypeValueErrors:
    """Error cases for single value parsing."""

    def test_malformed_json(self):
        with pytest.raises(ValueError, match="Failed to parse agtype value"):
            parse_agtype_value("{not valid json}")

    def test_malformed_vertex(self):
        with pytest.raises(ValueError, match="Failed to parse agtype value"):
            parse_agtype_value("{bad json::vertex")


# =============================================================================
# parse_agtype_collection — paths, nodes(), relationships()
# =============================================================================


class TestParseAgtypeCollection:
    """Collection agtype values: paths, nodes(), relationships()."""

    def test_none_returns_empty(self):
        assert parse_agtype_collection(None) == []

    def test_empty_string_returns_empty(self):
        assert parse_agtype_collection("") == []
        assert parse_agtype_collection("  ") == []

    def test_non_string_returns_empty(self):
        assert parse_agtype_collection(42) == []

    def test_path_collection(self):
        """Path: [vertex, edge, vertex, edge, vertex]"""
        raw = (
            '[{"id": 1, "label": "Artifact", "properties": {"mimir_id": "a1"}}::vertex, '
            '{"id": 10, "label": "Relation", "end_id": 2, "start_id": 1, '
            '"properties": {"relation_type": "derived_from"}}::edge, '
            '{"id": 2, "label": "Artifact", "properties": {"mimir_id": "a2"}}::vertex]'
        )
        result = parse_agtype_collection(raw)
        assert len(result) == 3
        assert result[0]["label"] == "Artifact"
        assert result[0]["properties"]["mimir_id"] == "a1"
        assert result[1]["label"] == "Relation"
        assert result[1]["properties"]["relation_type"] == "derived_from"
        assert result[2]["label"] == "Artifact"
        assert result[2]["properties"]["mimir_id"] == "a2"

    def test_nodes_collection(self):
        """nodes(path): [vertex, vertex, ...]"""
        raw = (
            '[{"id": 1, "label": "Artifact", "properties": {"mimir_id": "a1"}}::vertex, '
            '{"id": 2, "label": "Artifact", "properties": {"mimir_id": "a2"}}::vertex]'
        )
        result = parse_agtype_collection(raw)
        assert len(result) == 2
        assert all(r["label"] == "Artifact" for r in result)

    def test_relationships_collection(self):
        """relationships(path): [edge, edge, ...]"""
        raw = (
            '[{"id": 10, "label": "Relation", "end_id": 2, "start_id": 1, '
            '"properties": {"relation_type": "derived_from"}}::edge, '
            '{"id": 11, "label": "Relation", "end_id": 3, "start_id": 2, '
            '"properties": {"relation_type": "supports"}}::edge]'
        )
        result = parse_agtype_collection(raw)
        assert len(result) == 2
        assert result[0]["properties"]["relation_type"] == "derived_from"
        assert result[1]["properties"]["relation_type"] == "supports"

    def test_empty_json_array(self):
        result = parse_agtype_collection("[]")
        assert result == []

    def test_single_vertex_in_array(self):
        raw = '[{"id": 1, "label": "Artifact", "properties": {}}::vertex]'
        result = parse_agtype_collection(raw)
        assert len(result) == 1

    def test_longer_path(self):
        """A 3-hop path: v-e-v-e-v-e-v (7 elements)."""
        raw = (
            '[{"id": 1, "label": "Artifact", "properties": {"mimir_id": "a1"}}::vertex, '
            '{"id": 10, "label": "Relation", "end_id": 2, "start_id": 1, "properties": {"relation_type": "r1"}}::edge, '
            '{"id": 2, "label": "Artifact", "properties": {"mimir_id": "a2"}}::vertex, '
            '{"id": 11, "label": "Relation", "end_id": 3, "start_id": 2, "properties": {"relation_type": "r2"}}::edge, '
            '{"id": 3, "label": "Artifact", "properties": {"mimir_id": "a3"}}::vertex, '
            '{"id": 12, "label": "Relation", "end_id": 4, "start_id": 3, "properties": {"relation_type": "r3"}}::edge, '
            '{"id": 4, "label": "Artifact", "properties": {"mimir_id": "a4"}}::vertex]'
        )
        result = parse_agtype_collection(raw)
        assert len(result) == 7
        # Vertices at even indices, edges at odd
        assert result[0]["label"] == "Artifact"
        assert result[1]["label"] == "Relation"
        assert result[6]["properties"]["mimir_id"] == "a4"


# =============================================================================
# parse_agtype_collection — errors
# =============================================================================


class TestParseAgtypeCollectionErrors:
    """Error cases for collection parsing."""

    def test_malformed_json(self):
        with pytest.raises(ValueError, match="Failed to parse agtype collection"):
            parse_agtype_collection("[{bad json}::vertex]")

    def test_not_an_array(self):
        with pytest.raises(ValueError, match="Expected JSON array"):
            parse_agtype_collection('{"id": 1}')
