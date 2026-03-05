"""Integration tests for OllamaProvider with a running Ollama instance.

These are the primary confidence tests for this library.
They prove the actual promise: text goes in, correctly-dimensioned vector comes out.

Prerequisites:
    - Ollama running at http://localhost:11434
    - Model 'nomic-embed-text' pulled: ollama pull nomic-embed-text
"""

import httpx
import pytest

from mimir_embeddings.config import OllamaConfig
from mimir_embeddings.exceptions import ProviderError
from mimir_embeddings.providers.ollama import OllamaProvider

pytestmark = pytest.mark.integration


def ollama_available():
    """Check if Ollama is reachable."""
    try:
        httpx.get("http://localhost:11434/api/tags", timeout=2.0)
        return True
    except (httpx.ConnectError, httpx.TimeoutException):
        return False


skip_no_ollama = pytest.mark.skipif(
    not ollama_available(), reason="Ollama not available at localhost:11434"
)


@pytest.fixture
def config():
    return OllamaConfig(
        base_url="http://localhost:11434",
        model="nomic-embed-text",
        dimensions=768,
    )


@skip_no_ollama
async def test_generate_single_text_returns_correct_dimensions(config):
    """Promise: text in, correctly-dimensioned vector out."""
    async with OllamaProvider(config) as provider:
        result = await provider.generate("The quick brown fox jumps over the lazy dog.")
    assert len(result.embedding) == 768
    assert result.dimensions == 768
    assert result.model == "nomic-embed-text"


@skip_no_ollama
async def test_generate_batch_returns_correct_count_and_dimensions(config):
    """Promise: N texts in, N correctly-dimensioned results out."""
    texts = [
        "First document about science.",
        "Second document about history.",
        "Third document about mathematics.",
    ]
    async with OllamaProvider(config) as provider:
        results = await provider.generate_batch(texts)
    assert len(results) == 3
    for result in results:
        assert len(result.embedding) == 768
        assert result.dimensions == 768


@skip_no_ollama
async def test_generate_nonexistent_model_raises_provider_error():
    """Promise: bad model raises ProviderError, not httpx exception."""
    config = OllamaConfig(
        base_url="http://localhost:11434",
        model="nonexistent-model-that-does-not-exist",
        dimensions=768,
    )
    async with OllamaProvider(config) as provider:
        with pytest.raises(ProviderError) as exc_info:
            await provider.generate("hello")
    assert exc_info.value.provider_name == "ollama"


@skip_no_ollama
async def test_generate_result_fields_match_config(config):
    """Promise: result metadata matches provider configuration."""
    async with OllamaProvider(config) as provider:
        result = await provider.generate("test")
    assert result.model == config.model
    assert result.dimensions == config.dimensions
    assert result.token_count is None  # Ollama does not report token count