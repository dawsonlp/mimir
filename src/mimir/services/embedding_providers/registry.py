"""Embedding provider registry.

Manages registration and lookup of embedding providers.
Providers are registered at import time and can be looked up by name or model ID.
"""

import structlog

from mimir.services.embedding_providers.base import (
    EmbeddingModelInfo,
    EmbeddingProvider,
)

logger = structlog.get_logger()

# Global registry of providers
_providers: dict[str, EmbeddingProvider] = {}


def register_provider(provider: EmbeddingProvider) -> None:
    """Register an embedding provider.

    Args:
        provider: The provider instance to register
    """
    name = provider.provider_name
    _providers[name] = provider
    logger.info(
        "Registered embedding provider",
        provider=name,
        models=[m.model_id for m in provider.list_models()],
    )


def get_provider(name: str) -> EmbeddingProvider | None:
    """Get a provider by name.

    Args:
        name: Provider name (e.g., 'voyage', 'openai')

    Returns:
        Provider instance or None if not found
    """
    return _providers.get(name)


def get_provider_for_model(model_id: str) -> EmbeddingProvider | None:
    """Get the provider that supports a specific model.

    Args:
        model_id: Model identifier to look up

    Returns:
        Provider instance or None if no provider supports the model
    """
    for provider in _providers.values():
        if provider.get_model_info(model_id) is not None:
            return provider
    return None


def list_providers() -> list[str]:
    """List all registered provider names.

    Returns:
        List of provider names
    """
    return list(_providers.keys())


def list_all_models() -> list[EmbeddingModelInfo]:
    """List all available models from all providers.

    Returns:
        List of all model info objects
    """
    models = []
    for provider in _providers.values():
        if provider.is_configured():
            models.extend(provider.list_models())
    return models


def get_model_info(model_id: str) -> EmbeddingModelInfo | None:
    """Get model info by model ID from any provider.

    Args:
        model_id: Model identifier to look up

    Returns:
        Model info or None if not found
    """
    for provider in _providers.values():
        info = provider.get_model_info(model_id)
        if info is not None:
            return info
    return None


def get_configured_providers() -> list[EmbeddingProvider]:
    """Get all providers that are properly configured.

    Returns:
        List of configured provider instances
    """
    return [p for p in _providers.values() if p.is_configured()]


def get_default_model() -> EmbeddingModelInfo | None:
    """Get the default embedding model.

    Returns the first available model from configured providers,
    preferring Voyage AI models if available.

    Returns:
        Default model info or None if no models available
    """
    # Prefer Voyage AI if configured
    voyage = get_provider("voyage")
    if voyage and voyage.is_configured():
        models = voyage.list_models()
        if models:
            return models[0]

    # Fall back to any configured provider
    for provider in get_configured_providers():
        models = provider.list_models()
        if models:
            return models[0]

    return None
