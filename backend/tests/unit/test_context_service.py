"""
Unit tests for context_service.py - P1 Context Retrieval Service.

Tests focus on:
- Temporal filtering: complex date logic with edge cases
- Hints processing: business logic for context assembly
"""

import pytest
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from mimir.schemas.artifact import ArtifactResponse
from mimir.schemas.context import (
    ContextArtifact,
    ContextHints,
    TemporalHint,
    TemporalMode,
)
from mimir.services.context_service import (
    _apply_hints,
    _apply_temporal_filter,
)


def _make_context_artifact(days_ago: int, title: str = None) -> ContextArtifact:
    """Factory for context artifacts with specific ages."""
    now = datetime.now(timezone.utc)
    artifact = ArtifactResponse(
        id=uuid4(),
        tenant_id=1,
        artifact_type="document",
        parent_artifact_id=None,
        start_offset=None,
        end_offset=None,
        position_metadata=None,
        title=title or f"Doc from {days_ago} days ago",
        content="Sample content",
        content_hash=None,
        source=None,
        source_system=None,
        external_id=None,
        metadata=None,
        created_at=now - timedelta(days=days_ago),
    )
    return ContextArtifact(
        artifact=artifact,
        relation_path=[],
        distance=1,
        relevance_score=None,
        inclusion_reason="test",
    )


class TestTemporalFilter:
    """Test _apply_temporal_filter function.
    
    Temporal filtering has complex date boundary logic that is easy to
    get wrong (off-by-one, timezone issues, inclusive/exclusive ranges).
    """

    @pytest.fixture
    def artifacts_with_dates(self) -> list[ContextArtifact]:
        """Create context artifacts with various ages."""
        return [
            _make_context_artifact(1),    # Yesterday
            _make_context_artifact(7),    # Week ago
            _make_context_artifact(30),   # Month ago
            _make_context_artifact(90),   # 3 months ago
            _make_context_artifact(365),  # Year ago
        ]

    def test_recent_mode_filters_old(self, artifacts_with_dates: list[ContextArtifact]):
        """Recent mode with days_back filters older artifacts."""
        temporal = TemporalHint(mode=TemporalMode.RECENT, days_back=14)
        result = _apply_temporal_filter(artifacts_with_dates, temporal)
        
        # Should keep only yesterday and week ago
        assert len(result) == 2

    def test_historical_mode_filters_recent(self, artifacts_with_dates: list[ContextArtifact]):
        """Historical mode keeps only artifacts older than cutoff."""
        temporal = TemporalHint(mode=TemporalMode.HISTORICAL, days_back=60)
        result = _apply_temporal_filter(artifacts_with_dates, temporal)
        
        # Should keep 90 days and 365 days
        assert len(result) == 2

    def test_range_mode_filters_outside_range(self, artifacts_with_dates: list[ContextArtifact]):
        """Range mode filters artifacts outside date range."""
        now = datetime.now(timezone.utc)
        temporal = TemporalHint(
            mode=TemporalMode.RANGE,
            start_date=(now - timedelta(days=35)).date(),
            end_date=(now - timedelta(days=5)).date(),
        )
        result = _apply_temporal_filter(artifacts_with_dates, temporal)
        
        # Should keep week ago and month ago
        assert len(result) == 2

    def test_no_days_back_returns_all(self, artifacts_with_dates: list[ContextArtifact]):
        """If days_back not set, return all artifacts."""
        temporal = TemporalHint(mode=TemporalMode.RECENT, days_back=None)
        result = _apply_temporal_filter(artifacts_with_dates, temporal)
        assert len(result) == len(artifacts_with_dates)


class TestApplyHints:
    """Test the hints application pipeline.
    
    Tests verify that hints correctly filter/transform context artifacts.
    These are business rules that affect RAG context quality.
    """

    @pytest.fixture
    def sample_context_artifacts(self) -> list[ContextArtifact]:
        """Create sample context artifacts for hint testing."""
        return [_make_context_artifact(i * 10, f"Doc {i}") for i in range(10)]

    @pytest.mark.asyncio
    async def test_no_hints_returns_all(self, sample_context_artifacts: list[ContextArtifact]):
        """No hints should return all artifacts unchanged."""
        hints = ContextHints()
        result, applied, excluded = await _apply_hints(
            sample_context_artifacts, hints, tenant_id=1
        )
        
        assert len(result) == len(sample_context_artifacts)
        assert excluded == 0

    @pytest.mark.asyncio
    async def test_token_budget_limits_results(self, sample_context_artifacts: list[ContextArtifact]):
        """Token budget should limit number of artifacts.
        
        Critical for RAG: prevents context overflow in LLM calls.
        """
        # 500 tokens per artifact estimate, budget of 1500 = 3 artifacts max
        hints = ContextHints(token_budget=1500)
        result, applied, excluded = await _apply_hints(
            sample_context_artifacts, hints, tenant_id=1
        )
        
        assert len(result) == 3
        assert applied.token_budget_enforced is True
        assert excluded == 7

    @pytest.mark.asyncio
    async def test_temporal_filter_applied(self, sample_context_artifacts: list[ContextArtifact]):
        """Temporal focus should filter by date."""
        hints = ContextHints(
            temporal_focus=TemporalHint(mode=TemporalMode.RECENT, days_back=25)
        )
        result, applied, excluded = await _apply_hints(
            sample_context_artifacts, hints, tenant_id=1
        )
        
        assert applied.temporal_filter_applied is True
        # Doc 0 (0 days), Doc 1 (10 days), Doc 2 (20 days) should pass
        assert len(result) == 3