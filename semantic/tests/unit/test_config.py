"""Tests for configuration classes."""

import pytest

from mimir_embeddings.config import (
    OllamaConfig,
    OpenAIConfig,
    create_ollama_config,
    create_openai_config,
)
from mimir_embeddings.exceptions import ConfigurationError


def test_ollama_config_defaults():
    config = OllamaConfig()
    assert config.base_url == "http://localhost:11434"
    assert config.model == "nomic-embed-text"
    assert config.dimensions == 768
    assert config.timeout == 30.0


def test_ollama_config_explicit_override():
    config = OllamaConfig(model="mxbai-embed-large", dimensions=1024)
    assert config.model == "mxbai-embed-large"
    assert config.dimensions == 1024


def test_ollama_config_from_env(monkeypatch):
    monkeypatch.setenv("MIMIR_EMBEDDINGS_OLLAMA_MODEL", "custom-model")
    monkeypatch.setenv("MIMIR_EMBEDDINGS_OLLAMA_DIMENSIONS", "512")
    config = OllamaConfig()
    assert config.model == "custom-model"
    assert config.dimensions == 512


def test_openai_config_requires_api_key():
    """OpenAI config without api_key raises."""
    with pytest.raises(Exception):
        OpenAIConfig()


def test_openai_config_with_api_key():
    config = OpenAIConfig(api_key="sk-test-key")
    assert config.api_key.get_secret_value() == "sk-test-key"
    assert config.model == "text-embedding-3-small"
    assert config.dimensions == 1536


def test_openai_config_from_env(monkeypatch):
    monkeypatch.setenv("MIMIR_EMBEDDINGS_OPENAI_API_KEY", "sk-env-key")
    monkeypatch.setenv("MIMIR_EMBEDDINGS_OPENAI_MODEL", "text-embedding-3-large")
    config = OpenAIConfig()
    assert config.api_key.get_secret_value() == "sk-env-key"
    assert config.model == "text-embedding-3-large"


def test_openai_config_secret_str_hides_key():
    """SecretStr prevents accidental logging of API key."""
    config = OpenAIConfig(api_key="sk-secret-123")
    assert "sk-secret-123" not in str(config.api_key)
    assert "sk-secret-123" not in repr(config.api_key)


def test_create_ollama_config_factory():
    config = create_ollama_config(model="test-model")
    assert config.model == "test-model"


def test_create_openai_config_factory_missing_key_raises_configuration_error():
    with pytest.raises(ConfigurationError):
        create_openai_config()


def test_create_openai_config_factory_with_key():
    config = create_openai_config(api_key="sk-factory")
    assert config.api_key.get_secret_value() == "sk-factory"