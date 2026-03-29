"""Configuration for embedding providers using pydantic-settings."""

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from mimir_embeddings.exceptions import ConfigurationError


class OllamaConfig(BaseSettings):
    """Configuration for OllamaProvider.

    Loads from environment variables with MIMIR_EMBEDDINGS_OLLAMA_ prefix.
    All fields have defaults except none are strictly required.
    """

    model_config = SettingsConfigDict(env_prefix="MIMIR_EMBEDDINGS_OLLAMA_")

    base_url: str = "http://localhost:11434"
    model: str = "nomic-embed-text"
    dimensions: int = 768
    timeout: float = 30.0


class OpenAIConfig(BaseSettings):
    """Configuration for OpenAIProvider.

    Loads from environment variables with MIMIR_EMBEDDINGS_OPENAI_ prefix.
    api_key is required and has no default.
    """

    model_config = SettingsConfigDict(env_prefix="MIMIR_EMBEDDINGS_OPENAI_")

    api_key: SecretStr
    base_url: str = "https://api.openai.com/v1"
    model: str = "text-embedding-3-small"
    dimensions: int = 1536
    timeout: float = 30.0


def create_ollama_config(**overrides) -> OllamaConfig:
    """Create OllamaConfig, translating validation errors to ConfigurationError."""
    try:
        return OllamaConfig(**overrides)
    except Exception as exc:
        raise ConfigurationError(str(exc)) from exc


def create_openai_config(**overrides) -> OpenAIConfig:
    """Create OpenAIConfig, translating validation errors to ConfigurationError."""
    try:
        return OpenAIConfig(**overrides)
    except Exception as exc:
        raise ConfigurationError(str(exc)) from exc