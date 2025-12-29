"""Ollama embedding provider (V2)."""

import os

import httpx

from mimir.services.embedding_providers.base import (
    EmbeddingModelInfo,
    EmbeddingProvider,
    EmbeddingResult,
)

OLLAMA_MODELS = [
    EmbeddingModelInfo(
        model_id="nomic-embed-text",
        provider="ollama",
        display_name="Nomic Embed Text",
        dimensions=768,
        max_tokens=8192,
    ),
    EmbeddingModelInfo(
        model_id="mxbai-embed-large",
        provider="ollama",
        display_name="MixedBread Embed Large",
        dimensions=1024,
        max_tokens=512,
    ),
]


class OllamaProvider(EmbeddingProvider):
    """Ollama embedding provider (local models)."""

    def __init__(self):
        self._base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

    @property
    def provider_name(self) -> str:
        return "ollama"

    def list_models(self) -> list[EmbeddingModelInfo]:
        return OLLAMA_MODELS

    def get_model_info(self, model_id: str) -> EmbeddingModelInfo | None:
        for model in OLLAMA_MODELS:
            if model.model_id == model_id:
                return model
        return None

    def is_configured(self) -> bool:
        return True  # Ollama runs locally

    async def generate_embedding(self, text: str, model_id: str) -> EmbeddingResult:
        model_info = self.get_model_info(model_id)
        if not model_info:
            raise ValueError(f"Unknown model: {model_id}")

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self._base_url}/api/embeddings",
                json={"model": model_id, "prompt": text},
                timeout=120.0,
            )
            response.raise_for_status()
            data = response.json()

        embedding = data["embedding"]

        return EmbeddingResult(
            embedding=embedding,
            model_id=model_id,
            dimensions=len(embedding),
        )


ollama_provider = OllamaProvider()
