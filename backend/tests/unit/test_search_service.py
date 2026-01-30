"""
Unit tests for search_service.py - P2 Relation-Aware Search Filters.

Tests focus on _filter_results_by_relation - the core filtering logic
with edge cases around ordering, scoring, and ranking.
"""

import pytest
from datetime import datetime, timezone
from uuid import uuid4

from mimir.schemas.artifact import ArtifactResponse
from mimir.schemas.search import SearchResult
from mimir.services.search_service import _filter_results_by_relation


def _make_search_result(name: str, index: int) -> tuple[SearchResult, dict]:
    """Factory for search results with known UUIDs."""
    artifact_id = uuid4()
    artifact = ArtifactResponse(
        id=artifact_id,
        tenant_id=1,
        artifact_type="document",
        parent_artifact_id=None,
        start_offset=None,
        end_offset=None,
        position_metadata=None,
        title=f"Document {name}",
        content=f"Content of {name}",
        content_hash=None,
        source=None,
        source_system=None,
        external_id=None,
        metadata=None,
        created_at=datetime.now(timezone.utc),
    )
    # Original score decreases with index
    score = 1.0 - (index * 0.1)
    result = SearchResult(artifact=artifact, score=score, rank=index + 1)
    return result, {name: artifact_id}


class TestFilterResultsByRelation:
    """Test _filter_results_by_relation helper function.
    
    This function is critical for P2 relation-aware search. It must:
    - Correctly filter to related IDs
    - Preserve original search scores
    - Re-rank results after filtering
    Edge cases matter for search quality.
    """

    @pytest.fixture
    def sample_search_results(self) -> tuple[list[SearchResult], dict]:
        """Create sample search results with known UUIDs."""
        results = []
        uuid_map = {}
        for i, name in enumerate(["doc_a", "doc_b", "doc_c", "doc_d", "doc_e"]):
            result, mapping = _make_search_result(name, i)
            results.append(result)
            uuid_map.update(mapping)
        return results, uuid_map

    def test_filter_keeps_matching_results(self, sample_search_results):
        """Results with IDs in related_ids set should be kept."""
        results, uuid_map = sample_search_results
        related_ids = {uuid_map["doc_a"], uuid_map["doc_c"]}
        
        filtered = _filter_results_by_relation(results, related_ids)
        
        assert len(filtered) == 2
        filtered_ids = {r.artifact.id for r in filtered}
        assert uuid_map["doc_a"] in filtered_ids
        assert uuid_map["doc_c"] in filtered_ids

    def test_filter_preserves_original_scores(self, sample_search_results):
        """Original search scores should be preserved after filtering.
        
        Critical: scores come from search ranking, not relation filtering.
        """
        results, uuid_map = sample_search_results
        original_scores = {r.artifact.id: r.score for r in results}
        related_ids = {uuid_map["doc_a"], uuid_map["doc_d"]}
        
        filtered = _filter_results_by_relation(results, related_ids)
        
        for result in filtered:
            assert result.score == original_scores[result.artifact.id]

    def test_filter_reranks_results(self, sample_search_results):
        """Ranks should be reassigned sequentially after filtering."""
        results, uuid_map = sample_search_results
        # Keep doc_a (rank 1), doc_c (rank 3), doc_e (rank 5)
        related_ids = {uuid_map["doc_a"], uuid_map["doc_c"], uuid_map["doc_e"]}
        
        filtered = _filter_results_by_relation(results, related_ids)
        
        # New ranks should be 1, 2, 3
        ranks = [r.rank for r in filtered]
        assert ranks == [1, 2, 3]

    def test_filter_preserves_order(self, sample_search_results):
        """Results should maintain their relative order after filtering."""
        results, uuid_map = sample_search_results
        related_ids = {uuid_map["doc_b"], uuid_map["doc_d"], uuid_map["doc_e"]}
        
        filtered = _filter_results_by_relation(results, related_ids)
        
        # Order should be preserved: doc_b, doc_d, doc_e
        assert filtered[0].artifact.id == uuid_map["doc_b"]
        assert filtered[1].artifact.id == uuid_map["doc_d"]
        assert filtered[2].artifact.id == uuid_map["doc_e"]

    def test_empty_related_ids_returns_empty(self, sample_search_results):
        """Empty related_ids set should return empty results."""
        results, _ = sample_search_results
        filtered = _filter_results_by_relation(results, set())
        assert filtered == []

    def test_no_matches_returns_empty(self, sample_search_results):
        """If no results match related_ids, return empty."""
        results, _ = sample_search_results
        unrelated_ids = {uuid4(), uuid4(), uuid4()}
        
        filtered = _filter_results_by_relation(results, unrelated_ids)
        
        assert filtered == []