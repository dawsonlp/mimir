"""OpenAI embedding provider (V2)."""

import os

import httpx

from mimir.services.embedding_providers.base import (
    EmbeddingModelInfo,
    EmbeddingProvider,
    EmbeddingResult,
)

OPENAI_MODELS = [
    EmbeddingModelInfo(
        model_id="text-embedding-3-small",
        provider="openai",
        display_name="OpenAI Text Embedding 3 Small",
        dimensions=1536,
        max_tokens=8191,
    ),
    EmbeddingModelInfo(
        model_id="text-embedding-3-large",
        provider="openai",
        display_name="OpenAI Text Embedding 3 Large",
        dimensions=3072,
        max_tokens=8191,
    ),
]


class OpenAIProvider(EmbeddingProvider):
    """OpenAI embedding provider."""

    def __init__(self):
        self._api_key = os.getenv("OPENAI_API_KEY")

    @property
    def provider_name(self) -> str:
        return "openai"

    def list_models(self) -> list[EmbeddingModelInfo]:
        return OPENAI_MODELS

    def get_model_info(self, model_id: str) -> EmbeddingModelInfo | None:
        for model in OPENAI_MODELS:
            if model.model_id == model_id:
                return model
        return None

    def is_configured(self) -> bool:
        return bool(self._api_key)

    async def generate_embedding(self, text: str, model_id: str) -> EmbeddingResult:
        if not self._api_key:
            raise ValueError("OPENAI_API_KEY not configured")

        model_info = self.get_model_info(model_id)
        if not model_info:
            raise ValueError(f"Unknown model: {model_id}")

        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.openai.com/v1/embeddings",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={"input": text, "model": model_id},
                timeout=60.0,
            )
            response.raise_for_status()
            data = response.json()

        embedding = data["data"][0]["embedding"]
        tokens_used = data.get("usage", {}).get("total_tokens")

        return EmbeddingResult(
            embedding=embedding,
            model_id=model_id,
            dimensions=len(embedding),
            tokens_used=tokens_used,
        )


openai_provider = OpenAIProvider()
