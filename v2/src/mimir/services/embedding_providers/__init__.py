"""Embedding providers for Mímir V2."""

from mimir.services.embedding_providers.base import (
    EmbeddingModelInfo,
    EmbeddingProvider,
    EmbeddingResult,
)
from mimir.services.embedding_providers.ollama import ollama_provider
from mimir.services.embedding_providers.openai import openai_provider
from mimir.services.embedding_providers.registry import (
    generate_embedding,
    get_model_info,
    get_provider,
    list_all_models,
    list_providers,
    register_provider,
)

# Register providers
register_provider(openai_provider)
register_provider(ollama_provider)

__all__ = [
    "EmbeddingModelInfo",
    "EmbeddingProvider",
    "EmbeddingResult",
    "register_provider",
    "get_provider",
    "list_providers",
    "list_all_models",
    "get_model_info",
    "generate_embedding",
]
