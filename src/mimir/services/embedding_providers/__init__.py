"""Embedding providers - pluggable embedding generation backends."""

from mimir.services.embedding_providers.base import EmbeddingProvider
from mimir.services.embedding_providers.ollama import OllamaEmbeddingProvider
from mimir.services.embedding_providers.openai import OpenAIEmbeddingProvider
from mimir.services.embedding_providers.registry import (
    get_provider,
    list_providers,
    register_provider,
)
from mimir.services.embedding_providers.voyage import VoyageEmbeddingProvider

__all__ = [
    "EmbeddingProvider",
    "OllamaEmbeddingProvider",
    "OpenAIEmbeddingProvider",
    "VoyageEmbeddingProvider",
    "get_provider",
    "list_providers",
    "register_provider",
]
