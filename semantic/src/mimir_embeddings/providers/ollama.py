"""Ollama embedding provider."""

import httpx

from mimir_embeddings.config import OllamaConfig
from mimir_embeddings.exceptions import ProviderError
from mimir_embeddings.models import EmbeddingResult
from mimir_embeddings.providers.base import EmbeddingProvider
from mimir_embeddings.validation import validate_dimensions

_PROVIDER_NAME = "ollama"


class OllamaProvider(EmbeddingProvider):
    """Generate embeddings using a local Ollama instance.

    Uses POST /api/embed endpoint. Each instance is bound to a single model.
    """

    def __init__(self, config: OllamaConfig):
        self._config = config
        self._client = httpx.AsyncClient(
            base_url=config.base_url,
            timeout=config.timeout,
        )

    @property
    def dimensions(self) -> int:
        return self._config.dimensions

    @property
    def model_name(self) -> str:
        return self._config.model

    async def generate(self, text: str) -> EmbeddingResult:
        """Generate an embedding for a single text via Ollama."""
        data = await self._call_api(text)
        embedding = data["embeddings"][0]
        validate_dimensions(embedding, self.dimensions, model=self.model_name)
        return EmbeddingResult(
            embedding=embedding,
            model=self.model_name,
            dimensions=self.dimensions,
            token_count=None,
        )

    async def generate_batch(self, texts: list[str]) -> list[EmbeddingResult]:
        """Generate embeddings sequentially. Ollama processes one at a time."""
        results = []
        for text in texts:
            results.append(await self.generate(text))
        return results

    async def close(self) -> None:
        await self._client.aclose()

    async def _call_api(self, text: str) -> dict:
        """Make HTTP call to Ollama /api/embed endpoint."""
        try:
            response = await self._client.post(
                "/api/embed",
                json={"model": self._config.model, "input": text},
            )
            response.raise_for_status()
            return response.json()
        except httpx.ConnectError as exc:
            raise ProviderError(
                provider_name=_PROVIDER_NAME,
                detail=f"Cannot connect to Ollama at {self._config.base_url}: {exc}",
            ) from exc
        except httpx.TimeoutException as exc:
            raise ProviderError(
                provider_name=_PROVIDER_NAME,
                detail=f"Request timed out after {self._config.timeout}s",
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise ProviderError(
                provider_name=_PROVIDER_NAME,
                detail=exc.response.text or str(exc),
                status_code=exc.response.status_code,
            ) from exc