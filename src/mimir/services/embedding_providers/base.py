"""Base embedding provider interface.

All embedding providers must implement this interface to be compatible
with the embedding service.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class EmbeddingModelInfo:
    """Information about an embedding model.

    Attributes:
        model_id: Unique identifier for the model (e.g., "voyage-3")
        provider: Provider name (e.g., "voyage", "openai")
        display_name: Human-readable name
        dimensions: Output embedding dimensions
        max_tokens: Maximum input tokens supported
        description: Optional description of the model
    """

    model_id: str
    provider: str
    display_name: str
    dimensions: int
    max_tokens: int
    description: str = ""


@dataclass
class EmbeddingResult:
    """Result from embedding generation.

    Attributes:
        embedding: The embedding vector
        model_id: Model that generated the embedding
        dimensions: Actual dimensions of the embedding
        tokens_used: Number of tokens processed (if available)
    """

    embedding: list[float]
    model_id: str
    dimensions: int
    tokens_used: int | None = None


class EmbeddingProvider(ABC):
    """Abstract base class for embedding providers.

    All embedding providers must implement this interface.
    Providers are responsible for:
    - Listing available models
    - Generating embeddings for single texts
    - Optionally supporting batch embedding generation
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return the provider name (e.g., 'voyage', 'openai')."""
        ...

    @abstractmethod
    def list_models(self) -> list[EmbeddingModelInfo]:
        """List all available models from this provider.

        Returns:
            List of model information objects
        """
        ...

    @abstractmethod
    def get_model_info(self, model_id: str) -> EmbeddingModelInfo | None:
        """Get information about a specific model.

        Args:
            model_id: The model identifier

        Returns:
            Model info or None if not found
        """
        ...

    @abstractmethod
    async def generate_embedding(self, text: str, model_id: str) -> EmbeddingResult:
        """Generate an embedding for a single text.

        Args:
            text: Text to embed
            model_id: Model to use for embedding

        Returns:
            Embedding result with vector and metadata

        Raises:
            ValueError: If model is not supported or configuration is invalid
            httpx.HTTPStatusError: If API request fails
        """
        ...

    async def generate_embeddings_batch(
        self, texts: list[str], model_id: str
    ) -> list[EmbeddingResult]:
        """Generate embeddings for multiple texts.

        Default implementation calls generate_embedding for each text.
        Providers can override this for more efficient batch processing.

        Args:
            texts: List of texts to embed
            model_id: Model to use for embedding

        Returns:
            List of embedding results (one per input text)
        """
        results = []
        for text in texts:
            result = await self.generate_embedding(text, model_id)
            results.append(result)
        return results

    def supports_batch(self) -> bool:
        """Check if provider has native batch support.

        Returns:
            True if provider has optimized batch embedding
        """
        return False

    def is_configured(self) -> bool:
        """Check if provider is properly configured (e.g., API keys).

        Returns:
            True if provider can be used
        """
        return True
