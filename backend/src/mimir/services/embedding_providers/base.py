"""Base embedding provider interface (V2)."""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class EmbeddingModelInfo:
    """Information about an embedding model."""

    model_id: str
    provider: str
    display_name: str
    dimensions: int
    max_tokens: int
    description: str = ""


@dataclass
class EmbeddingResult:
    """Result from embedding generation."""

    embedding: list[float]
    model_id: str
    dimensions: int
    tokens_used: int | None = None


class EmbeddingProvider(ABC):
    """Abstract base class for embedding providers."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return the provider name."""
        ...

    @abstractmethod
    def list_models(self) -> list[EmbeddingModelInfo]:
        """List all available models."""
        ...

    @abstractmethod
    def get_model_info(self, model_id: str) -> EmbeddingModelInfo | None:
        """Get information about a specific model."""
        ...

    @abstractmethod
    async def generate_embedding(self, text: str, model_id: str) -> EmbeddingResult:
        """Generate an embedding for a single text."""
        ...

    async def generate_embeddings_batch(
        self, texts: list[str], model_id: str
    ) -> list[EmbeddingResult]:
        """Generate embeddings for multiple texts."""
        results = []
        for text in texts:
            result = await self.generate_embedding(text, model_id)
            results.append(result)
        return results

    def supports_batch(self) -> bool:
        """Check if provider has native batch support."""
        return False

    def is_configured(self) -> bool:
        """Check if provider is properly configured."""
        return True
