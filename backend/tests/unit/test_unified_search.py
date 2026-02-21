"""Unit tests for unified search endpoint strategy inference and schema validation.

Phase 3 Enhancement (2026-02-13):
Tests the pure _infer_search_strategy() function and UnifiedSearchRequest schema
without any database or I/O dependencies.
"""

from uuid import uuid4

import pytest
from fastapi import HTTPException

from mimir.routers.search import _infer_search_strategy
from mimir.schemas.search import SearchStrategy, UnifiedSearchRequest

# =============================================================================
# Helper: build UnifiedSearchRequest with minimal boilerplate
# =============================================================================

SAMPLE_VECTOR = [0.1, 0.2, 0.3]
SAMPLE_UUID = uuid4()
SAMPLE_EMBEDDING_TYPE = "nomic-embed-text"


def _make_request(**kwargs) -> UnifiedSearchRequest:
    """Build UnifiedSearchRequest with only the specified fields."""
    return UnifiedSearchRequest(**kwargs)


# =============================================================================
# Strategy Inference: Valid Combinations
# =============================================================================


class TestInferSearchStrategyValid:
    """Test that valid parameter combinations infer the correct strategy."""

    def test_infer_fulltext_query_only(self):
        """query only → FULLTEXT."""
        request = _make_request(query="test search")
        assert _infer_search_strategy(request) == SearchStrategy.FULLTEXT

    def test_infer_semantic_query_vector_with_embedding_type(self):
        """query_vector + embedding_type → SEMANTIC."""
        request = _make_request(
            query_vector=SAMPLE_VECTOR,
            embedding_type=SAMPLE_EMBEDDING_TYPE,
        )
        assert _infer_search_strategy(request) == SearchStrategy.SEMANTIC

    def test_infer_hybrid_query_and_vector_with_embedding_type(self):
        """query + query_vector + embedding_type → HYBRID."""
        request = _make_request(
            query="test search",
            query_vector=SAMPLE_VECTOR,
            embedding_type=SAMPLE_EMBEDDING_TYPE,
        )
        assert _infer_search_strategy(request) == SearchStrategy.HYBRID

    def test_infer_similar_similar_to_with_embedding_type(self):
        """similar_to + embedding_type → SIMILAR."""
        request = _make_request(
            similar_to=SAMPLE_UUID,
            embedding_type=SAMPLE_EMBEDDING_TYPE,
        )
        assert _infer_search_strategy(request) == SearchStrategy.SIMILAR

    def test_fulltext_with_filters_still_fulltext(self):
        """Filters don't affect strategy inference."""
        request = _make_request(
            query="test",
            artifact_types=["document"],
            metadata_filters={"language": "python"},
            scope_artifact_id=SAMPLE_UUID,
            limit=10,
            offset=5,
        )
        assert _infer_search_strategy(request) == SearchStrategy.FULLTEXT

    def test_semantic_with_filters_still_semantic(self):
        """Filters don't affect strategy inference."""
        request = _make_request(
            query_vector=SAMPLE_VECTOR,
            embedding_type=SAMPLE_EMBEDDING_TYPE,
            artifact_types=["chunk"],
            related_to=SAMPLE_UUID,
        )
        assert _infer_search_strategy(request) == SearchStrategy.SEMANTIC


# =============================================================================
# Strategy Inference: Error Cases
# =============================================================================


class TestInferSearchStrategyErrors:
    """Test that invalid parameter combinations produce clear 422 errors."""

    def test_error_no_ranking_input(self):
        """No ranking inputs → 422 NO_RANKING_INPUT."""
        request = _make_request()
        with pytest.raises(HTTPException) as exc_info:
            _infer_search_strategy(request)
        assert exc_info.value.status_code == 422
        assert exc_info.value.detail["code"] == "NO_RANKING_INPUT"

    def test_error_no_ranking_input_with_filters_only(self):
        """Only filters, no ranking inputs → 422 NO_RANKING_INPUT."""
        request = _make_request(
            artifact_types=["document"],
            metadata_filters={"language": "python"},
            limit=10,
        )
        with pytest.raises(HTTPException) as exc_info:
            _infer_search_strategy(request)
        assert exc_info.value.status_code == 422
        assert exc_info.value.detail["code"] == "NO_RANKING_INPUT"

    def test_error_vector_plus_similar(self):
        """query_vector + similar_to → 422 AMBIGUOUS_RANKING."""
        request = _make_request(
            query_vector=SAMPLE_VECTOR,
            similar_to=SAMPLE_UUID,
            embedding_type=SAMPLE_EMBEDDING_TYPE,
        )
        with pytest.raises(HTTPException) as exc_info:
            _infer_search_strategy(request)
        assert exc_info.value.status_code == 422
        assert exc_info.value.detail["code"] == "AMBIGUOUS_RANKING"

    def test_error_query_plus_similar(self):
        """query + similar_to → 422 RESERVED_COMBINATION."""
        request = _make_request(
            query="test",
            similar_to=SAMPLE_UUID,
            embedding_type=SAMPLE_EMBEDDING_TYPE,
        )
        with pytest.raises(HTTPException) as exc_info:
            _infer_search_strategy(request)
        assert exc_info.value.status_code == 422
        assert exc_info.value.detail["code"] == "RESERVED_COMBINATION"

    def test_error_all_three_ranking_inputs(self):
        """query + query_vector + similar_to → 422 AMBIGUOUS_RANKING.

        The vector + similar check fires first (both present).
        """
        request = _make_request(
            query="test",
            query_vector=SAMPLE_VECTOR,
            similar_to=SAMPLE_UUID,
            embedding_type=SAMPLE_EMBEDDING_TYPE,
        )
        with pytest.raises(HTTPException) as exc_info:
            _infer_search_strategy(request)
        assert exc_info.value.status_code == 422
        assert exc_info.value.detail["code"] == "AMBIGUOUS_RANKING"

    def test_error_semantic_missing_embedding_type(self):
        """query_vector without embedding_type → 422 MISSING_EMBEDDING_TYPE."""
        request = _make_request(query_vector=SAMPLE_VECTOR)
        with pytest.raises(HTTPException) as exc_info:
            _infer_search_strategy(request)
        assert exc_info.value.status_code == 422
        assert exc_info.value.detail["code"] == "MISSING_EMBEDDING_TYPE"
        assert "query_vector" in exc_info.value.detail["detail"]
        assert "semantic" in exc_info.value.detail["detail"]

    def test_error_similar_missing_embedding_type(self):
        """similar_to without embedding_type → 422 MISSING_EMBEDDING_TYPE."""
        request = _make_request(similar_to=SAMPLE_UUID)
        with pytest.raises(HTTPException) as exc_info:
            _infer_search_strategy(request)
        assert exc_info.value.status_code == 422
        assert exc_info.value.detail["code"] == "MISSING_EMBEDDING_TYPE"
        assert "similar_to" in exc_info.value.detail["detail"]
        assert "similar" in exc_info.value.detail["detail"]

    def test_error_hybrid_missing_embedding_type(self):
        """query + query_vector without embedding_type → 422 MISSING_EMBEDDING_TYPE."""
        request = _make_request(query="test", query_vector=SAMPLE_VECTOR)
        with pytest.raises(HTTPException) as exc_info:
            _infer_search_strategy(request)
        assert exc_info.value.status_code == 422
        assert exc_info.value.detail["code"] == "MISSING_EMBEDDING_TYPE"
        assert "hybrid" in exc_info.value.detail["detail"]


# =============================================================================
# Schema Validation
# =============================================================================


class TestUnifiedSearchRequestValidation:
    """Test Pydantic schema validation on UnifiedSearchRequest."""

    def test_empty_query_rejected(self):
        """query with empty string is rejected (min_length=1)."""
        with pytest.raises(Exception):
            UnifiedSearchRequest(query="")

    def test_limit_minimum(self):
        """limit below 1 is rejected."""
        with pytest.raises(Exception):
            UnifiedSearchRequest(query="test", limit=0)

    def test_limit_maximum(self):
        """limit above 100 is rejected."""
        with pytest.raises(Exception):
            UnifiedSearchRequest(query="test", limit=101)

    def test_offset_negative_rejected(self):
        """Negative offset is rejected."""
        with pytest.raises(Exception):
            UnifiedSearchRequest(query="test", offset=-1)

    def test_similarity_threshold_bounds(self):
        """similarity_threshold must be 0.0-1.0."""
        with pytest.raises(Exception):
            UnifiedSearchRequest(
                query_vector=[0.1], embedding_type="test-type", similarity_threshold=1.5
            )
        with pytest.raises(Exception):
            UnifiedSearchRequest(
                query_vector=[0.1],
                embedding_type="test-type",
                similarity_threshold=-0.1,
            )

    def test_semantic_weight_bounds(self):
        """semantic_weight must be 0.0-1.0."""
        with pytest.raises(Exception):
            UnifiedSearchRequest(
                query="test",
                query_vector=[0.1],
                embedding_type="test-type",
                semantic_weight=2.0,
            )

    def test_embedding_type_min_length(self):
        """embedding_type must be at least 3 characters."""
        with pytest.raises(Exception):
            UnifiedSearchRequest(query_vector=[0.1], embedding_type="ab")

    def test_embedding_type_max_length(self):
        """embedding_type must be at most 50 characters."""
        with pytest.raises(Exception):
            UnifiedSearchRequest(query_vector=[0.1], embedding_type="a" * 51)

    def test_valid_defaults(self):
        """Default values are sensible."""
        request = _make_request(query="test")
        assert request.limit == 20
        assert request.offset == 0
        assert request.similarity_threshold == 0.0
        assert request.rrf_k == 60
        assert request.semantic_weight == 0.5
        assert request.artifact_types is None
        assert request.metadata_filters is None
        assert request.scope_artifact_id is None
        assert request.related_to is None
        assert request.relation_type is None
        assert request.query_vector is None
        assert request.similar_to is None
        assert request.embedding_type is None

    def test_valid_uuid_in_similar_to(self):
        """similar_to accepts valid UUID."""
        uid = uuid4()
        request = _make_request(similar_to=uid, embedding_type="test-type")
        assert request.similar_to == uid

    def test_valid_metadata_filters(self):
        """metadata_filters accepts dict with str and list[str] values."""
        filters = {"language": "python", "tags": ["api", "core"]}
        request = _make_request(query="test", metadata_filters=filters)
        assert request.metadata_filters == filters


# =============================================================================
# SearchStrategy Enum
# =============================================================================


class TestSearchStrategyEnum:
    """Test SearchStrategy enum values."""

    def test_values(self):
        assert SearchStrategy.FULLTEXT == "fulltext"
        assert SearchStrategy.SEMANTIC == "semantic"
        assert SearchStrategy.HYBRID == "hybrid"
        assert SearchStrategy.SIMILAR == "similar"

    def test_from_string(self):
        assert SearchStrategy("fulltext") == SearchStrategy.FULLTEXT
        assert SearchStrategy("semantic") == SearchStrategy.SEMANTIC
        assert SearchStrategy("hybrid") == SearchStrategy.HYBRID
        assert SearchStrategy("similar") == SearchStrategy.SIMILAR
