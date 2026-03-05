"""Tests for exception hierarchy."""

from mimir_embeddings.exceptions import (
    ConfigurationError,
    DimensionMismatchError,
    MimirEmbeddingsError,
    ProviderError,
)


def test_all_exceptions_inherit_from_base():
    assert issubclass(ProviderError, MimirEmbeddingsError)
    assert issubclass(DimensionMismatchError, MimirEmbeddingsError)
    assert issubclass(ConfigurationError, MimirEmbeddingsError)


def test_base_inherits_from_exception():
    assert issubclass(MimirEmbeddingsError, Exception)


def test_provider_error_attributes():
    err = ProviderError(provider_name="ollama", detail="Connection refused")
    assert err.provider_name == "ollama"
    assert err.detail == "Connection refused"
    assert err.status_code is None
    assert "ollama" in str(err)
    assert "Connection refused" in str(err)


def test_provider_error_with_status_code():
    err = ProviderError(
        provider_name="openai", detail="Unauthorized", status_code=401
    )
    assert err.status_code == 401
    assert "401" in str(err)
    assert "openai" in str(err)


def test_provider_error_preserves_cause():
    original = ConnectionError("network down")
    try:
        raise ProviderError(
            provider_name="ollama", detail="network down"
        ) from original
    except ProviderError as exc:
        assert exc.__cause__ is original


def test_dimension_mismatch_error_attributes():
    err = DimensionMismatchError(expected=768, actual=512, model="nomic-embed-text")
    assert err.expected == 768
    assert err.actual == 512
    assert err.model == "nomic-embed-text"
    assert "768" in str(err)
    assert "512" in str(err)
    assert "nomic-embed-text" in str(err)


def test_configuration_error():
    err = ConfigurationError("Missing API key")
    assert "Missing API key" in str(err)
    assert isinstance(err, MimirEmbeddingsError)