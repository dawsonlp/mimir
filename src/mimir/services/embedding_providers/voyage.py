"""Voyage AI embedding provider.

Voyage AI provides state-of-the-art embedding models and is
Anthropic's recommended embedding API for use with Claude.

API Documentation: https://docs.voyageai.com/docs/embeddings
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

# Voyage AI API endpoint
VOYAGE_API_URL = "https://api.voyageai.com/v1/embeddings"

# Available Voyage AI models with their specifications
# Reference: https://docs.voyageai.com/docs/embeddings
VOYAGE_MODELS: dict[str, EmbeddingModelInfo] = {
    "voyage-3-large": EmbeddingModelInfo(
        model_id="voyage-3-large",
        provider="voyage",
        display_name="Voyage 3 Large",
        dimensions=1024,
        max_tokens=32000,
        description="Most powerful generalist embedding model. Best for RAG and search.",
    ),
    "voyage-3": EmbeddingModelInfo(
        model_id="voyage-3",
        provider="voyage",
        display_name="Voyage 3",
        dimensions=1024,
        max_tokens=32000,
        description="Optimized for latency and quality. Great general-purpose model.",
    ),
    "voyage-3-lite": EmbeddingModelInfo(
        model_id="voyage-3-lite",
        provider="voyage",
        display_name="Voyage 3 Lite",
        dimensions=512,
        max_tokens=32000,
        description="Optimized for latency. Cost-effective option.",
    ),
    "voyage-code-3": EmbeddingModelInfo(
        model_id="voyage-code-3",
        provider="voyage",
        display_name="Voyage Code 3",
        dimensions=1024,
        max_tokens=32000,
        description="Optimized for code retrieval. Best for code search.",
    ),
    "voyage-finance-2": EmbeddingModelInfo(
        model_id="voyage-finance-2",
        provider="voyage",
        display_name="Voyage Finance 2",
        dimensions=1024,
        max_tokens=32000,
        description="Optimized for financial documents and queries.",
    ),
    "voyage-law-2": EmbeddingModelInfo(
        model_id="voyage-law-2",
        provider="voyage",
        display_name="Voyage Law 2",
        dimensions=1024,
        max_tokens=32000,
        description="Optimized for legal documents and queries.",
    ),
    "voyage-multilingual-2": EmbeddingModelInfo(
        model_id="voyage-multilingual-2",
        provider="voyage",
        display_name="Voyage Multilingual 2",
        dimensions=1024,
        max_tokens=32000,
        description="Optimized for multilingual content across many languages.",
    ),
}


class VoyageProvider(EmbeddingProvider):
    """Voyage AI embedding provider.

    Uses Voyage AI's embedding API to generate embeddings.
    Requires VOYAGE_API_KEY environment variable.
    """

    @property
    def provider_name(self) -> str:
        """Return the provider name."""
        return "voyage"

    def list_models(self) -> list[EmbeddingModelInfo]:
        """List all available Voyage AI models."""
        return list(VOYAGE_MODELS.values())

    def get_model_info(self, model_id: str) -> EmbeddingModelInfo | None:
        """Get information about a specific model."""
        return VOYAGE_MODELS.get(model_id)

    def is_configured(self) -> bool:
        """Check if Voyage AI API key is configured."""
        settings = get_settings()
        return settings.voyage_api_key is not None

    def supports_batch(self) -> bool:
        """Voyage AI supports batch embedding."""
        return True

    async def generate_embedding(self, text: str, model_id: str) -> EmbeddingResult:
        """Generate an embedding using Voyage AI.

        Args:
            text: Text to embed
            model_id: Voyage AI model to use

        Returns:
            Embedding result with vector and metadata

        Raises:
            ValueError: If API key not configured or model not supported
            httpx.HTTPStatusError: If API request fails
        """
        settings = get_settings()
        if not settings.voyage_api_key:
            raise ValueError("VOYAGE_API_KEY not configured")

        model_info = self.get_model_info(model_id)
        if not model_info:
            raise ValueError(f"Model {model_id} is not a Voyage AI model")

        async with httpx.AsyncClient() as client:
            response = await client.post(
                VOYAGE_API_URL,
                headers={
                    "Authorization": f"Bearer {settings.voyage_api_key.get_secret_value()}",
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
            "Generated Voyage AI embedding",
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
        """Generate embeddings for multiple texts using Voyage AI.

        Voyage AI supports batch embedding natively for efficiency.

        Args:
            texts: List of texts to embed
            model_id: Voyage AI model to use

        Returns:
            List of embedding results (one per input text)

        Raises:
            ValueError: If API key not configured or model not supported
            httpx.HTTPStatusError: If API request fails
        """
        settings = get_settings()
        if not settings.voyage_api_key:
            raise ValueError("VOYAGE_API_KEY not configured")

        model_info = self.get_model_info(model_id)
        if not model_info:
            raise ValueError(f"Model {model_id} is not a Voyage AI model")

        async with httpx.AsyncClient() as client:
            response = await client.post(
                VOYAGE_API_URL,
                headers={
                    "Authorization": f"Bearer {settings.voyage_api_key.get_secret_value()}",
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
            "Generated Voyage AI batch embeddings",
            model=model_id,
            count=len(results),
            total_tokens=tokens_used,
        )

        return results
