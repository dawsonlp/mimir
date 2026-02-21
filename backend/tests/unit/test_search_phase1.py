"""
Unit tests for Phase 1 Search Infrastructure enhancements.

Tests cover three features:
1. Pagination (offset) — schema validation and service-level offset/limit slicing
2. Metadata filtering — _build_metadata_filter SQL generation
3. Hierarchy scoping — _build_scope_filter SQL generation

Pure function tests (no I/O, no mocks). Database-dependent tests live in integration/.
"""

import json
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from mimir.schemas.artifact import ArtifactResponse
from mimir.schemas.search import (
    SearchResult,
    UnifiedSearchRequest,
)
from mimir.services.search_service import (
    _build_metadata_filter,
    _build_scope_filter,
)

# =============================================================================
# Helpers
# =============================================================================


def _make_artifact(
    artifact_id: UUID | None = None,
    metadata: dict | None = None,
    parent_artifact_id: UUID | None = None,
) -> ArtifactResponse:
    """Factory for ArtifactResponse with sensible defaults."""
    return ArtifactResponse(
        id=artifact_id or uuid4(),
        tenant_id=1,
        artifact_type="document",
        parent_artifact_id=parent_artifact_id,
        start_offset=None,
        end_offset=None,
        position_metadata=None,
        title="Test Document",
        content="Test content",
        content_hash=None,
        source=None,
        source_system=None,
        external_id=None,
        metadata=metadata,
        created_at=datetime.now(UTC),
    )


def _make_search_result(
    score: float = 0.9,
    artifact_id: UUID | None = None,
    metadata: dict | None = None,
) -> SearchResult:
    """Factory for SearchResult."""
    return SearchResult(
        artifact=_make_artifact(artifact_id=artifact_id, metadata=metadata),
        score=score,
        rank=1,
    )


# =============================================================================
# 1. Pagination — Schema Validation
# =============================================================================


class TestPaginationSchemas:
    """Test that offset is properly accepted in UnifiedSearchRequest."""

    def test_semantic_search_request_default_offset(self):
        """UnifiedSearchRequest (semantic params) should default offset to 0."""
        req = UnifiedSearchRequest(
            query_vector=[0.1, 0.2, 0.3],
            embedding_type="nomic-embed-text",
        )
        assert req.offset == 0

    def test_semantic_search_request_custom_offset(self):
        """UnifiedSearchRequest (semantic params) should accept custom offset."""
        req = UnifiedSearchRequest(
            query_vector=[0.1, 0.2, 0.3],
            embedding_type="nomic-embed-text",
            offset=50,
        )
        assert req.offset == 50

    def test_semantic_search_request_negative_offset_rejected(self):
        """UnifiedSearchRequest should reject negative offset."""
        with pytest.raises(Exception):  # ValidationError
            UnifiedSearchRequest(
                query_vector=[0.1, 0.2, 0.3],
                embedding_type="nomic-embed-text",
                offset=-1,
            )

    def test_hybrid_search_request_default_offset(self):
        """UnifiedSearchRequest (hybrid params) should default offset to 0."""
        req = UnifiedSearchRequest(
            query="test",
            query_vector=[0.1, 0.2, 0.3],
            embedding_type="nomic-embed-text",
        )
        assert req.offset == 0

    def test_hybrid_search_request_custom_offset(self):
        """UnifiedSearchRequest (hybrid params) should accept custom offset."""
        req = UnifiedSearchRequest(
            query="test",
            query_vector=[0.1, 0.2, 0.3],
            embedding_type="nomic-embed-text",
            offset=25,
        )
        assert req.offset == 25

    def test_hybrid_search_request_negative_offset_rejected(self):
        """UnifiedSearchRequest should reject negative offset."""
        with pytest.raises(Exception):
            UnifiedSearchRequest(
                query="test",
                query_vector=[0.1, 0.2, 0.3],
                embedding_type="nomic-embed-text",
                offset=-5,
            )


class TestPaginationSlicing:
    """Test offset/limit slicing behavior on in-memory result lists.

    These test the slicing pattern used by semantic_search, hybrid_search,
    and similar_artifacts for offset/limit after scoring.
    """

    def test_offset_zero_returns_first_page(self):
        """offset=0 returns the first `limit` results."""
        results = [_make_search_result(score=1.0 - i * 0.1) for i in range(10)]
        offset, limit = 0, 3
        page = results[offset : offset + limit]
        assert len(page) == 3
        assert page[0].score == 1.0

    def test_offset_skips_n_results(self):
        """offset=N skips the first N results."""
        results = [_make_search_result(score=1.0 - i * 0.1) for i in range(10)]
        offset, limit = 3, 3
        page = results[offset : offset + limit]
        assert len(page) == 3
        assert page[0].score == pytest.approx(0.7)

    def test_offset_beyond_total_returns_empty(self):
        """offset beyond total count returns empty list."""
        results = [_make_search_result(score=1.0 - i * 0.1) for i in range(5)]
        offset, limit = 100, 10
        page = results[offset : offset + limit]
        assert page == []

    def test_offset_at_total_returns_empty(self):
        """offset equal to total count returns empty list."""
        results = [_make_search_result(score=1.0 - i * 0.1) for i in range(5)]
        offset, limit = 5, 10
        page = results[offset : offset + limit]
        assert page == []

    def test_offset_partial_last_page(self):
        """offset near end returns partial page."""
        results = [_make_search_result(score=1.0 - i * 0.1) for i in range(5)]
        offset, limit = 3, 10
        page = results[offset : offset + limit]
        assert len(page) == 2


# =============================================================================
# 2. Metadata Filtering — _build_metadata_filter
# =============================================================================


class TestBuildMetadataFilter:
    """Test _build_metadata_filter SQL generation.

    This function builds parameterized JSONB containment clauses for GIN index use.
    """

    def test_empty_filters_returns_empty_string(self):
        """Empty dict produces no SQL fragment."""
        params = []
        result = _build_metadata_filter({}, params)
        assert result == ""
        assert params == []

    def test_single_scalar_key(self):
        """Single key=value produces one containment condition."""
        params = []
        result = _build_metadata_filter({"language": "python"}, params)
        assert "metadata @> %s::jsonb" in result
        assert len(params) == 1
        assert json.loads(params[0]) == {"language": "python"}

    def test_multiple_keys_and_across(self):
        """Multiple keys produce AND-joined containment conditions."""
        params = []
        result = _build_metadata_filter(
            {"language": "python", "framework": "fastapi"},
            params,
        )
        # Should have AND between two conditions
        assert result.count("metadata @> %s::jsonb") == 2
        assert " AND " in result
        assert len(params) == 2
        parsed_params = [json.loads(p) for p in params]
        assert {"language": "python"} in parsed_params
        assert {"framework": "fastapi"} in parsed_params

    def test_array_value_or_within(self):
        """Array value produces OR-joined conditions for that key."""
        params = []
        result = _build_metadata_filter(
            {"tags": ["api", "core"]},
            params,
        )
        assert result.count("metadata @> %s::jsonb") == 2
        assert " OR " in result
        assert len(params) == 2
        parsed_params = [json.loads(p) for p in params]
        assert {"tags": "api"} in parsed_params
        assert {"tags": "core"} in parsed_params

    def test_mixed_scalar_and_array(self):
        """Mix of scalar and array produces correct AND/OR structure."""
        params = []
        result = _build_metadata_filter(
            {"language": "python", "tags": ["api", "core"]},
            params,
        )
        # 1 scalar + 2 array = 3 params
        assert len(params) == 3
        # Should have AND between scalar clause and array clause group
        assert " AND " in result
        # Array clause should be wrapped in parentheses with OR
        assert "(" in result
        assert " OR " in result

    def test_empty_array_value_no_clause(self):
        """Empty array value produces no clause for that key."""
        params = []
        result = _build_metadata_filter({"tags": []}, params)
        # Empty array produces no OR parts, so no clause
        assert result == ""
        assert params == []

    def test_params_are_appended_not_replaced(self):
        """Params list should be appended to, preserving existing entries."""
        params = ["existing_param"]
        _build_metadata_filter({"language": "python"}, params)
        assert params[0] == "existing_param"
        assert len(params) == 2

    def test_sql_injection_safe_keys_and_values(self):
        """Keys and values with SQL-dangerous characters are safely JSON-encoded."""
        params = []
        _build_metadata_filter(
            {"'; DROP TABLE artifact; --": "value'; DELETE FROM artifact;"},
            params,
        )
        # The key/value are JSON-encoded, not interpolated into SQL
        assert len(params) == 1
        parsed = json.loads(params[0])
        assert "'; DROP TABLE artifact; --" in parsed
        # The SQL template only uses %s placeholders
        assert "DROP" not in _build_metadata_filter(
            {"'; DROP TABLE artifact; --": "value"},
            [],
        )

    def test_result_starts_with_and(self):
        """Non-empty result starts with ' AND ' for safe concatenation."""
        params = []
        result = _build_metadata_filter({"key": "value"}, params)
        assert result.startswith(" AND ")


# =============================================================================
# 3. Hierarchy Scoping — _build_scope_filter
# =============================================================================


class TestBuildScopeFilter:
    """Test _build_scope_filter SQL fragment generation."""

    def test_single_descendant(self):
        """Single UUID produces IN clause with one placeholder."""
        uid = uuid4()
        params = []
        result = _build_scope_filter({uid}, params)
        assert "IN (%s)" in result
        assert len(params) == 1
        assert params[0] == str(uid)

    def test_multiple_descendants(self):
        """Multiple UUIDs produce IN clause with multiple placeholders."""
        uids = {uuid4(), uuid4(), uuid4()}
        params = []
        result = _build_scope_filter(uids, params)
        assert result.count("%s") == 3
        assert len(params) == 3

    def test_empty_set_returns_impossible_condition(self):
        """Empty set produces impossible WHERE condition (no results)."""
        params = []
        result = _build_scope_filter(set(), params)
        assert "IS NULL" in result
        assert params == []

    def test_alias_prefix(self):
        """Alias prefix is applied to the column reference."""
        uid = uuid4()
        params = []
        result = _build_scope_filter({uid}, params, alias="a.")
        assert "a.id IN" in result

    def test_no_alias_default(self):
        """Without alias, uses bare 'id' column reference."""
        uid = uuid4()
        params = []
        result = _build_scope_filter({uid}, params)
        assert " id IN" in result
        # Should NOT have a dot prefix
        assert "a.id" not in result

    def test_params_are_appended(self):
        """Params list should be appended to, preserving existing entries."""
        uid = uuid4()
        params = ["existing"]
        _build_scope_filter({uid}, params)
        assert params[0] == "existing"
        assert len(params) == 2

    def test_result_starts_with_and(self):
        """Non-empty result starts with ' AND ' for safe concatenation."""
        uid = uuid4()
        params = []
        result = _build_scope_filter({uid}, params)
        assert result.startswith(" AND ")

    def test_empty_set_with_alias(self):
        """Empty set with alias produces correctly aliased impossible condition."""
        params = []
        result = _build_scope_filter(set(), params, alias="a.")
        assert "a.id IS NULL" in result


# =============================================================================
# 4. Schema Validation — metadata_filters and scope_artifact_id
# =============================================================================


class TestMetadataFiltersSchema:
    """Test metadata_filters field on UnifiedSearchRequest."""

    def test_semantic_request_accepts_metadata_filters(self):
        """UnifiedSearchRequest (semantic) accepts metadata_filters dict."""
        req = UnifiedSearchRequest(
            query_vector=[0.1, 0.2],
            embedding_type="nomic-embed-text",
            metadata_filters={"language": "python"},
        )
        assert req.metadata_filters == {"language": "python"}

    def test_semantic_request_metadata_filters_default_none(self):
        """metadata_filters defaults to None."""
        req = UnifiedSearchRequest(
            query_vector=[0.1, 0.2],
            embedding_type="nomic-embed-text",
        )
        assert req.metadata_filters is None

    def test_semantic_request_metadata_filters_array_values(self):
        """metadata_filters accepts array values for OR semantics."""
        req = UnifiedSearchRequest(
            query_vector=[0.1, 0.2],
            embedding_type="nomic-embed-text",
            metadata_filters={"tags": ["api", "core"]},
        )
        assert req.metadata_filters["tags"] == ["api", "core"]

    def test_hybrid_request_accepts_metadata_filters(self):
        """UnifiedSearchRequest (hybrid) accepts metadata_filters dict."""
        req = UnifiedSearchRequest(
            query="test",
            query_vector=[0.1, 0.2],
            embedding_type="nomic-embed-text",
            metadata_filters={"framework": "fastapi", "tags": ["v2"]},
        )
        assert req.metadata_filters["framework"] == "fastapi"


class TestScopeArtifactIdSchema:
    """Test scope_artifact_id field on UnifiedSearchRequest."""

    def test_semantic_request_accepts_scope_artifact_id(self):
        """UnifiedSearchRequest (semantic) accepts scope_artifact_id UUID."""
        scope_id = uuid4()
        req = UnifiedSearchRequest(
            query_vector=[0.1, 0.2],
            embedding_type="nomic-embed-text",
            scope_artifact_id=scope_id,
        )
        assert req.scope_artifact_id == scope_id

    def test_semantic_request_scope_default_none(self):
        """scope_artifact_id defaults to None."""
        req = UnifiedSearchRequest(
            query_vector=[0.1, 0.2],
            embedding_type="nomic-embed-text",
        )
        assert req.scope_artifact_id is None

    def test_hybrid_request_accepts_scope_artifact_id(self):
        """UnifiedSearchRequest (hybrid) accepts scope_artifact_id UUID."""
        scope_id = uuid4()
        req = UnifiedSearchRequest(
            query="test",
            query_vector=[0.1, 0.2],
            embedding_type="nomic-embed-text",
            scope_artifact_id=scope_id,
        )
        assert req.scope_artifact_id == scope_id


# =============================================================================
# 5. Router — _parse_metadata_filters
# =============================================================================


class TestParseMetadataFilters:
    """Test the router's JSON query param parser for metadata_filters."""

    def test_none_input_returns_none(self):
        """None input returns None."""
        from mimir.routers.search import _parse_metadata_filters

        assert _parse_metadata_filters(None) is None

    def test_empty_string_returns_none(self):
        """Empty string returns None."""
        from mimir.routers.search import _parse_metadata_filters

        assert _parse_metadata_filters("") is None

    def test_valid_json_parsed(self):
        """Valid JSON string is parsed to dict."""
        from mimir.routers.search import _parse_metadata_filters

        result = _parse_metadata_filters('{"language": "python"}')
        assert result == {"language": "python"}

    def test_array_values_parsed(self):
        """Array values in JSON are preserved."""
        from mimir.routers.search import _parse_metadata_filters

        result = _parse_metadata_filters('{"tags": ["api", "core"]}')
        assert result == {"tags": ["api", "core"]}

    def test_invalid_json_raises_400(self):
        """Invalid JSON raises HTTPException 400."""
        from fastapi import HTTPException

        from mimir.routers.search import _parse_metadata_filters

        with pytest.raises(HTTPException) as exc_info:
            _parse_metadata_filters("{not valid json}")
        assert exc_info.value.status_code == 400

    def test_non_dict_json_raises_400(self):
        """Non-dict JSON (e.g., array) raises HTTPException 400."""
        from fastapi import HTTPException

        from mimir.routers.search import _parse_metadata_filters

        with pytest.raises(HTTPException) as exc_info:
            _parse_metadata_filters('["not", "a", "dict"]')
        assert exc_info.value.status_code == 400

    def test_non_string_value_raises_400(self):
        """Non-string value (e.g., int) raises HTTPException 400."""
        from fastapi import HTTPException

        from mimir.routers.search import _parse_metadata_filters

        with pytest.raises(HTTPException) as exc_info:
            _parse_metadata_filters('{"count": 42}')
        assert exc_info.value.status_code == 400

    def test_mixed_array_types_raises_400(self):
        """Array with non-string elements raises HTTPException 400."""
        from fastapi import HTTPException

        from mimir.routers.search import _parse_metadata_filters

        with pytest.raises(HTTPException) as exc_info:
            _parse_metadata_filters('{"tags": ["valid", 123]}')
        assert exc_info.value.status_code == 400
