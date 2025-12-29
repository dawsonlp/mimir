"""Embedding provider registry (V2)."""

from mimir.services.embedding_providers.base import (
    EmbeddingModelInfo,
    EmbeddingProvider,
    EmbeddingResult,
)

_providers: dict[str, EmbeddingProvider] = {}


def register_provider(provider: EmbeddingProvider) -> None:
    """Register an embedding provider."""
    _providers[provider.provider_name] = provider


def get_provider(name: str) -> EmbeddingProvider | None:
    """Get provider by name."""
    return _providers.get(name)


def list_providers() -> list[str]:
    """List registered provider names."""
    return list(_providers.keys())


def list_all_models() -> list[EmbeddingModelInfo]:
    """List all models from all providers."""
    models = []
    for provider in _providers.values():
        if provider.is_configured():
            models.extend(provider.list_models())
    return models


def get_model_info(model_id: str) -> EmbeddingModelInfo | None:
    """Get model info from any provider."""
    for provider in _providers.values():
        info = provider.get_model_info(model_id)
        if info:
            return info
    return None


async def generate_embedding(text: str, model_id: str) -> EmbeddingResult:
    """Generate embedding using appropriate provider."""
    for provider in _providers.values():
        if provider.get_model_info(model_id) and provider.is_configured():
            return await provider.generate_embedding(text, model_id)
    raise ValueError(f"No configured provider for model: {model_id}")
