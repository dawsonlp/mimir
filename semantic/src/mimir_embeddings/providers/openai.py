"""OpenAI embedding provider."""

import httpx

from mimir_embeddings.config import OpenAIConfig
from mimir_embeddings.exceptions import ProviderError
from mimir_embeddings.models import EmbeddingResult
from mimir_embeddings.providers.base import EmbeddingProvider
from mimir_embeddings.validation import validate_dimensions

_PROVIDER_NAME = "openai"


class OpenAIProvider(EmbeddingProvider):
    """Generate embeddings using the OpenAI embeddings API.

    Supports native batching — generate_batch() sends all texts in one HTTP call.
    Each instance is bound to a single model.
    """

    def __init__(self, config: OpenAIConfig):
        self._config = config
        self._client = httpx.AsyncClient(
            base_url=config.base_url,
            timeout=config.timeout,
            headers={
                "Authorization": f"Bearer {config.api_key.get_secret_value()}",
                "Content-Type": "application/json",
            },
        )

    @property
    def dimensions(self) -> int:
        return self._config.dimensions

    @property
    def model_name(self) -> str:
        return self._config.model

    async def generate(self, text: str) -> EmbeddingResult:
        """Generate an embedding for a single text via OpenAI."""
        data = await self._call_api(text)
        embedding = data["data"][0]["embedding"]
        validate_dimensions(embedding, self.dimensions, model=self.model_name)
        token_count = data.get("usage", {}).get("total_tokens")
        return EmbeddingResult(
            embedding=embedding,
            model=self.model_name,
            dimensions=self.dimensions,
            token_count=token_count,
        )

    async def generate_batch(self, texts: list[str]) -> list[EmbeddingResult]:
        """Generate embeddings for multiple texts in a single API call."""
        data = await self._call_api(texts)
        # Sort by index to guarantee input-order results
        sorted_items = sorted(data["data"], key=lambda item: item["index"])
        total_tokens = data.get("usage", {}).get("total_tokens")
        # Distribute token count evenly across batch results
        per_item_tokens = (
            total_tokens // len(sorted_items)
            if total_tokens is not None and len(sorted_items) > 0
            else None
        )
        results = []
        for item in sorted_items:
            embedding = item["embedding"]
            validate_dimensions(embedding, self.dimensions, model=self.model_name)
            results.append(
                EmbeddingResult(
                    embedding=embedding,
                    model=self.model_name,
                    dimensions=self.dimensions,
                    token_count=per_item_tokens,
                )
            )
        return results

    async def close(self) -> None:
        await self._client.aclose()

    async def _call_api(self, input_data: str | list[str]) -> dict:
        """Make HTTP call to OpenAI embeddings endpoint."""
        try:
            response = await self._client.post(
                "/embeddings",
                json={
                    "model": self._config.model,
                    "input": input_data,
                    "dimensions": self._config.dimensions,
                },
            )
            response.raise_for_status()
            return response.json()
        except httpx.ConnectError as exc:
            raise ProviderError(
                provider_name=_PROVIDER_NAME,
                detail=f"Cannot connect to OpenAI API at {self._config.base_url}: {exc}",
            ) from exc
        except httpx.TimeoutException as exc:
            raise ProviderError(
                provider_name=_PROVIDER_NAME,
                detail=f"Request timed out after {self._config.timeout}s",
            ) from exc
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            detail = exc.response.text or str(exc)
            if status == 401:
                detail = "Invalid API key or unauthorized"
            elif status == 429:
                detail = "Rate limited by OpenAI API"
            raise ProviderError(
                provider_name=_PROVIDER_NAME,
                detail=detail,
                status_code=status,
            ) from exc