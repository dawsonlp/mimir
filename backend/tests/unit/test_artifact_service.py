"""
Unit tests for artifact_service.py - P0 Batch Artifact Retrieval.

Tests focus on content hashing - a pure function with edge cases
that matter for deduplication behavior.
"""

import pytest

from mimir.services.artifact_service import _hash_content


class TestContentHashing:
    """Test _hash_content helper function for deduplication support.
    
    Content hashing is critical for detecting duplicates. These tests
    verify edge cases that could cause false duplicates or missed matches.
    """

    def test_none_returns_none(self):
        """None content should return None hash."""
        assert _hash_content(None) is None

    def test_empty_string_produces_hash(self):
        """Empty string should produce a valid hash."""
        result = _hash_content("")
        assert result is not None
        assert len(result) == 64  # SHA-256 produces 64 hex chars

    def test_same_content_same_hash(self):
        """Identical content should produce identical hashes."""
        content = "Test content for hashing"
        hash1 = _hash_content(content)
        hash2 = _hash_content(content)
        assert hash1 == hash2

    def test_different_content_different_hash(self):
        """Different content should produce different hashes."""
        hash1 = _hash_content("Content A")
        hash2 = _hash_content("Content B")
        assert hash1 != hash2

    def test_whitespace_matters(self):
        """Whitespace differences should produce different hashes.
        
        Important: prevents false deduplication of trimmed vs untrimmed content.
        """
        hash1 = _hash_content("test")
        hash2 = _hash_content(" test")
        hash3 = _hash_content("test ")
        assert hash1 != hash2
        assert hash1 != hash3
        assert hash2 != hash3

    def test_unicode_content(self):
        """Unicode content should hash correctly."""
        result = _hash_content("Unicode: 日本語 🎉 ñ")
        assert result is not None
        assert len(result) == 64