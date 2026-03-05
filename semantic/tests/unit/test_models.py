"""Tests for EmbeddingResult domain object."""

import pytest

from mimir_embeddings.models import EmbeddingResult


def test_embedding_result_construction():
    result = EmbeddingResult(
        embedding=[0.1, 0.2, 0.3],
        model="test-model",
        dimensions=3,
        token_count=5,
    )
    assert result.embedding == [0.1, 0.2, 0.3]
    assert result.model == "test-model"
    assert result.dimensions == 3
    assert result.token_count == 5


def test_embedding_result_token_count_defaults_to_none():
    result = EmbeddingResult(embedding=[1.0], model="m", dimensions=1)
    assert result.token_count is None


def test_embedding_result_is_frozen():
    result = EmbeddingResult(embedding=[1.0], model="m", dimensions=1)
    with pytest.raises(AttributeError):
        result.model = "other"


def test_embedding_result_equality():
    a = EmbeddingResult(embedding=[1.0, 2.0], model="m", dimensions=2)
    b = EmbeddingResult(embedding=[1.0, 2.0], model="m", dimensions=2)
    assert a == b


def test_embedding_result_inequality_different_model():
    a = EmbeddingResult(embedding=[1.0], model="a", dimensions=1)
    b = EmbeddingResult(embedding=[1.0], model="b", dimensions=1)
    assert a != b