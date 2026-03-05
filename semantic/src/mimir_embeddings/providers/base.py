"""Base embedding provider interface."""

from abc import ABC, abstractmethod

from mimir_embeddings.models import EmbeddingResult


class EmbeddingProvider(ABC):
    """Base class for embedding providers.

    Each instance is bound to a single model. Applications needing
    multiple models create multiple provider instances.

    Supports async context manager for resource cleanup::

        async with OllamaProvider(config) as provider:
            result = await provider.generate("hello")
    """

    @abstractmethod
    async def generate(self, text: str) -> EmbeddingResult:
        """Generate an embedding for a single text.

        Raises:
            ProviderError: HTTP call failed.
            DimensionMismatchError: Returned vector has wrong dimensions.
        """

    @abstractmethod
    async def generate_batch(self, texts: list[str]) -> list[EmbeddingResult]:
        """Generate embeddings for multiple texts.

        Returns results in the same order as inputs.

        Raises:
            ProviderError: HTTP call failed.
            DimensionMismatchError: Any returned vector has wrong dimensions.
        """

    @property
    @abstractmethod
    def dimensions(self) -> int:
        """Expected embedding dimensions for this provider's model."""

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Model identifier string."""

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        await self.close()

    async def close(self) -> None:
        """Release HTTP client resources. Override in implementations."""