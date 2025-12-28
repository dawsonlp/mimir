"""Embedding providers - pluggable embedding generation backends."""

from mimir.services.embedding_providers.base import EmbeddingProvider
from mimir.services.embedding_providers.ollama import OllamaEmbeddingProvider
from mimir.services.embedding_providers.openai import OpenAIProvider
from mimir.services.embedding_providers.registry import (
    get_provider,
    list_providers,
    register_provider,
)
from mimir.services.embedding_providers.voyage import VoyageProvider

__all__ = [
    "EmbeddingProvider",
    "OllamaEmbeddingProvider",
    "OpenAIProvider",
    "VoyageProvider",
    "get_provider",
    "list_providers",
    "register_provider",
]
