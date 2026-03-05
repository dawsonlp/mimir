"""Mimir Embeddings — embedding generation library for Mimir.

Provides provider abstraction over Ollama and OpenAI for converting
text into vectors. Mechanism, not policy.
"""

from importlib.metadata import PackageNotFoundError, version

from mimir_embeddings.config import OllamaConfig, OpenAIConfig
from mimir_embeddings.exceptions import (
    ConfigurationError,
    DimensionMismatchError,
    MimirEmbeddingsError,
    ProviderError,
)
from mimir_embeddings.models import EmbeddingResult
from mimir_embeddings.providers.base import EmbeddingProvider
from mimir_embeddings.providers.ollama import OllamaProvider
from mimir_embeddings.providers.openai import OpenAIProvider
from mimir_embeddings.validation import validate_dimensions

try:
    __version__ = version("mimir-embeddings")
except PackageNotFoundError:
    __version__ = "dev"

__all__ = [
    "EmbeddingProvider",
    "EmbeddingResult",
    "OllamaConfig",
    "OllamaProvider",
    "OpenAIConfig",
    "OpenAIProvider",
    "ConfigurationError",
    "DimensionMismatchError",
    "MimirEmbeddingsError",
    "ProviderError",
    "validate_dimensions",
    "__version__",
]