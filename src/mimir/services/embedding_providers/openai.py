"""OpenAI embedding provider.

Provides embeddings using OpenAI's text-embedding models.

API Documentation: https://platform.openai.com/docs/guides/embeddings
"""

import httpx
import structlog

from mimir.config import get_settings
from mimir.services.embedding_providers.base import (
    EmbeddingModelInfo,
    EmbeddingProvider,
    EmbeddingResult,
)

logger = structlog.get_logger()

# OpenAI API endpoint
OPENAI_API_URL = "https://api.openai.com/v1/embeddings"

# Available OpenAI embedding models with their specifications
OPENAI_MODELS: dict[str, EmbeddingModelInfo] = {
    "text-embedding-3-small": EmbeddingModelInfo(
        model_id="text-embedding-3-small",
        provider="openai",
        display_name="Text Embedding 3 Small",
        dimensions=1536,
        max_tokens=8191,
        description="Efficient, cost-effective embedding model.",
    ),
    "text-embedding-3-large": EmbeddingModelInfo(
        model_id="text-embedding-3-large",
        provider="openai",
        display_name="Text Embedding 3 Large",
        dimensions=3072,
        max_tokens=8191,
        description="Highest quality embedding model. Note: dimensions truncated to 1536 for storage.",
    ),
    "text-embedding-ada-002": EmbeddingModelInfo(
        model_id="text-embedding-ada-002",
        provider="openai",
        display_name="Text Embedding Ada 002",
        dimensions=1536,
        max_tokens=8191,
        description="Legacy model. Use text-embedding-3-small for new projects.",
    ),
}


class OpenAIProvider(EmbeddingProvider):
    """OpenAI embedding provider.

    Uses OpenAI's embedding API to generate embeddings.
    Requires OPENAI_API_KEY environment variable.
    """

    @property
    def provider_name(self) -> str:
        """Return the provider name."""
        return "openai"

    def list_models(self) -> list[EmbeddingModelInfo]:
        """List all available OpenAI models."""
        return list(OPENAI_MODELS.values())

    def get_model_info(self, model_id: str) -> EmbeddingModelInfo | None:
        """Get information about a specific model."""
        return OPENAI_MODELS.get(model_id)

    def is_configured(self) -> bool:
        """Check if OpenAI API key is configured."""
        settings = get_settings()
        return settings.openai_api_key is not None

    def supports_batch(self) -> bool:
        """OpenAI supports batch embedding."""
        return True

    async def generate_embedding(self, text: str, model_id: str) -> EmbeddingResult:
        """Generate an embedding using OpenAI.

        Args:
            text: Text to embed
            model_id: OpenAI model to use

        Returns:
            Embedding result with vector and metadata

        Raises:
            ValueError: If API key not configured or model not supported
            httpx.HTTPStatusError: If API request fails
        """
        settings = get_settings()
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY not configured")

        model_info = self.get_model_info(model_id)
        if not model_info:
            raise ValueError(f"Model {model_id} is not an OpenAI model")

        async with httpx.AsyncClient() as client:
            response = await client.post(
                OPENAI_API_URL,
                headers={
                    "Authorization": f"Bearer {settings.openai_api_key.get_secret_value()}",
                    "Content-Type": "application/json",
                },
                json={
                    "input": text,
                    "model": model_id,
                },
                timeout=60.0,
            )
            response.raise_for_status()
            data = response.json()

        embedding = data["data"][0]["embedding"]
        tokens_used = data.get("usage", {}).get("total_tokens")

        await logger.ainfo(
            "Generated OpenAI embedding",
            model=model_id,
            dimensions=len(embedding),
            tokens_used=tokens_used,
        )

        return EmbeddingResult(
            embedding=embedding,
            model_id=model_id,
            dimensions=len(embedding),
            tokens_used=tokens_used,
        )

    async def generate_embeddings_batch(
        self, texts: list[str], model_id: str
    ) -> list[EmbeddingResult]:
        """Generate embeddings for multiple texts using OpenAI.

        OpenAI supports batch embedding natively for efficiency.

        Args:
            texts: List of texts to embed
            model_id: OpenAI model to use

        Returns:
            List of embedding results (one per input text)

        Raises:
            ValueError: If API key not configured or model not supported
            httpx.HTTPStatusError: If API request fails
        """
        settings = get_settings()
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY not configured")

        model_info = self.get_model_info(model_id)
        if not model_info:
            raise ValueError(f"Model {model_id} is not an OpenAI model")

        async with httpx.AsyncClient() as client:
            response = await client.post(
                OPENAI_API_URL,
                headers={
                    "Authorization": f"Bearer {settings.openai_api_key.get_secret_value()}",
                    "Content-Type": "application/json",
                },
                json={
                    "input": texts,
                    "model": model_id,
                },
                timeout=120.0,
            )
            response.raise_for_status()
            data = response.json()

        # Sort by index to maintain order
        embeddings_data = sorted(data["data"], key=lambda x: x["index"])
        tokens_used = data.get("usage", {}).get("total_tokens")

        results = []
        for emb_data in embeddings_data:
            embedding = emb_data["embedding"]
            results.append(
                EmbeddingResult(
                    embedding=embedding,
                    model_id=model_id,
                    dimensions=len(embedding),
                    tokens_used=tokens_used // len(texts) if tokens_used else None,
                )
            )

        await logger.ainfo(
            "Generated OpenAI batch embeddings",
            model=model_id,
            count=len(results),
            total_tokens=tokens_used,
        )

        return results
