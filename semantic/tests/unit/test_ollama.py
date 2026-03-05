"""Tests for OllamaProvider — outcome-focused with mocked HTTP."""

import httpx
import pytest
import respx

from mimir_embeddings.config import OllamaConfig
from mimir_embeddings.exceptions import DimensionMismatchError, ProviderError
from mimir_embeddings.providers.ollama import OllamaProvider


@pytest.fixture
def config():
    return OllamaConfig(
        base_url="http://test-ollama:11434",
        model="test-model",
        dimensions=3,
        timeout=5.0,
    )


@pytest.fixture
def provider(config):
    return OllamaProvider(config)


def _embed_route(base_url="http://test-ollama:11434"):
    return respx.post(f"{base_url}/api/embed")


# --- Outcome: given text, return correct EmbeddingResult ---


@respx.mock
async def test_generate_valid_text_returns_correct_result(provider):
    _embed_route().respond(json={"embeddings": [[0.1, 0.2, 0.3]]})
    result = await provider.generate("hello")
    assert len(result.embedding) == 3
    assert result.dimensions == 3
    assert result.model == "test-model"
    assert result.token_count is None


@respx.mock
async def test_generate_batch_returns_results_for_each_input(provider):
    route = _embed_route()
    route.side_effect = [
        httpx.Response(200, json={"embeddings": [[0.1, 0.2, 0.3]]}),
        httpx.Response(200, json={"embeddings": [[0.4, 0.5, 0.6]]}),
    ]
    results = await provider.generate_batch(["hello", "world"])
    assert len(results) == 2
    assert results[0].embedding == [0.1, 0.2, 0.3]
    assert results[1].embedding == [0.4, 0.5, 0.6]


# --- Outcome: dimension mismatch raises with diagnosable context ---


@respx.mock
async def test_generate_wrong_dimensions_raises_with_context(provider):
    _embed_route().respond(json={"embeddings": [[0.1, 0.2]]})
    with pytest.raises(DimensionMismatchError) as exc_info:
        await provider.generate("hello")
    assert exc_info.value.expected == 3
    assert exc_info.value.actual == 2
    assert exc_info.value.model == "test-model"


# --- Outcome: transport failures wrapped in ProviderError ---


@respx.mock
async def test_generate_connection_refused_raises_provider_error(provider):
    _embed_route().mock(side_effect=httpx.ConnectError("Connection refused"))
    with pytest.raises(ProviderError) as exc_info:
        await provider.generate("hello")
    assert exc_info.value.provider_name == "ollama"
    assert "Connection refused" in exc_info.value.detail
    assert exc_info.value.__cause__ is not None


@respx.mock
async def test_generate_timeout_raises_provider_error(provider):
    _embed_route().mock(side_effect=httpx.ReadTimeout("timed out"))
    with pytest.raises(ProviderError) as exc_info:
        await provider.generate("hello")
    assert exc_info.value.provider_name == "ollama"
    assert "timed out" in exc_info.value.detail


@respx.mock
async def test_generate_http_404_raises_provider_error_with_status(provider):
    _embed_route().respond(status_code=404, text="model not found")
    with pytest.raises(ProviderError) as exc_info:
        await provider.generate("hello")
    assert exc_info.value.status_code == 404
    assert exc_info.value.provider_name == "ollama"


@respx.mock
async def test_generate_http_500_raises_provider_error(provider):
    _embed_route().respond(status_code=500, text="internal error")
    with pytest.raises(ProviderError) as exc_info:
        await provider.generate("hello")
    assert exc_info.value.status_code == 500


# --- Outcome: context manager closes resources ---


@respx.mock
async def test_context_manager_closes_client():
    config = OllamaConfig(
        base_url="http://test-ollama:11434",
        model="test-model",
        dimensions=3,
    )
    async with OllamaProvider(config) as provider:
        _embed_route().respond(json={"embeddings": [[0.1, 0.2, 0.3]]})
        result = await provider.generate("hello")
        assert result.dimensions == 3
    # After exit, client should be closed
    assert provider._client.is_closed