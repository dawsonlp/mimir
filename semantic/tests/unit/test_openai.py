"""Tests for OpenAIProvider — outcome-focused with mocked HTTP."""

import httpx
import pytest
import respx

from mimir_embeddings.config import OpenAIConfig
from mimir_embeddings.exceptions import DimensionMismatchError, ProviderError
from mimir_embeddings.providers.openai import OpenAIProvider


@pytest.fixture
def config():
    return OpenAIConfig(
        api_key="sk-test-key",
        base_url="http://test-openai:8080/v1",
        model="test-embed",
        dimensions=3,
        timeout=5.0,
    )


@pytest.fixture
def provider(config):
    return OpenAIProvider(config)


def _embed_route(base_url="http://test-openai:8080/v1"):
    return respx.post(f"{base_url}/embeddings")


def _single_response(embedding, total_tokens=10):
    return {
        "data": [{"embedding": embedding, "index": 0}],
        "usage": {"total_tokens": total_tokens},
    }


def _batch_response(embeddings, total_tokens=30):
    return {
        "data": [
            {"embedding": emb, "index": i} for i, emb in enumerate(embeddings)
        ],
        "usage": {"total_tokens": total_tokens},
    }


# --- Outcome: given text, return correct EmbeddingResult ---


@respx.mock
async def test_generate_valid_text_returns_correct_result(provider):
    _embed_route().respond(json=_single_response([0.1, 0.2, 0.3], total_tokens=5))
    result = await provider.generate("hello")
    assert len(result.embedding) == 3
    assert result.dimensions == 3
    assert result.model == "test-embed"
    assert result.token_count == 5


@respx.mock
async def test_generate_batch_returns_results_for_each_input(provider):
    response = _batch_response(
        [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6], [0.7, 0.8, 0.9]],
        total_tokens=15,
    )
    _embed_route().respond(json=response)
    results = await provider.generate_batch(["a", "b", "c"])
    assert len(results) == 3
    assert results[0].embedding == [0.1, 0.2, 0.3]
    assert results[2].embedding == [0.7, 0.8, 0.9]
    # Token count distributed evenly: 15 // 3 = 5
    assert all(r.token_count == 5 for r in results)


@respx.mock
async def test_generate_batch_results_sorted_by_index(provider):
    """Even if API returns items out of order, results match input order."""
    response = {
        "data": [
            {"embedding": [0.7, 0.8, 0.9], "index": 2},
            {"embedding": [0.1, 0.2, 0.3], "index": 0},
            {"embedding": [0.4, 0.5, 0.6], "index": 1},
        ],
        "usage": {"total_tokens": 9},
    }
    _embed_route().respond(json=response)
    results = await provider.generate_batch(["a", "b", "c"])
    assert results[0].embedding == [0.1, 0.2, 0.3]
    assert results[1].embedding == [0.4, 0.5, 0.6]
    assert results[2].embedding == [0.7, 0.8, 0.9]


# --- Outcome: dimension mismatch raises with diagnosable context ---


@respx.mock
async def test_generate_wrong_dimensions_raises_with_context(provider):
    _embed_route().respond(json=_single_response([0.1, 0.2]))
    with pytest.raises(DimensionMismatchError) as exc_info:
        await provider.generate("hello")
    assert exc_info.value.expected == 3
    assert exc_info.value.actual == 2
    assert exc_info.value.model == "test-embed"


# --- Outcome: transport failures wrapped in ProviderError ---


@respx.mock
async def test_generate_connection_refused_raises_provider_error(provider):
    _embed_route().mock(side_effect=httpx.ConnectError("Connection refused"))
    with pytest.raises(ProviderError) as exc_info:
        await provider.generate("hello")
    assert exc_info.value.provider_name == "openai"
    assert exc_info.value.__cause__ is not None


@respx.mock
async def test_generate_timeout_raises_provider_error(provider):
    _embed_route().mock(side_effect=httpx.ReadTimeout("timed out"))
    with pytest.raises(ProviderError) as exc_info:
        await provider.generate("hello")
    assert exc_info.value.provider_name == "openai"
    assert "timed out" in exc_info.value.detail


@respx.mock
async def test_generate_http_401_raises_provider_error_auth(provider):
    _embed_route().respond(status_code=401, text="Unauthorized")
    with pytest.raises(ProviderError) as exc_info:
        await provider.generate("hello")
    assert exc_info.value.status_code == 401
    assert "unauthorized" in exc_info.value.detail.lower()


@respx.mock
async def test_generate_http_429_raises_provider_error_rate_limit(provider):
    _embed_route().respond(status_code=429, text="Too Many Requests")
    with pytest.raises(ProviderError) as exc_info:
        await provider.generate("hello")
    assert exc_info.value.status_code == 429
    assert "rate limit" in exc_info.value.detail.lower()


@respx.mock
async def test_generate_http_500_raises_provider_error(provider):
    _embed_route().respond(status_code=500, text="Internal Server Error")
    with pytest.raises(ProviderError) as exc_info:
        await provider.generate("hello")
    assert exc_info.value.status_code == 500


# --- Outcome: context manager closes resources ---


@respx.mock
async def test_context_manager_closes_client():
    config = OpenAIConfig(
        api_key="sk-test",
        base_url="http://test-openai:8080/v1",
        model="test-embed",
        dimensions=3,
    )
    async with OpenAIProvider(config) as provider:
        _embed_route().respond(json=_single_response([0.1, 0.2, 0.3]))
        result = await provider.generate("hello")
        assert result.dimensions == 3
    assert provider._client.is_closed