"""Exception hierarchy for mimir-embeddings.

Three concrete exceptions cover all failure modes:
- ProviderError: HTTP/network failures communicating with providers
- DimensionMismatchError: Returned vector has wrong dimensions
- ConfigurationError: Invalid or missing configuration
"""


class MimirEmbeddingsError(Exception):
    """Base exception for all mimir-embeddings errors."""


class ProviderError(MimirEmbeddingsError):
    """Provider HTTP call failed (network, auth, rate limit, server error).

    Always raised with ``raise ProviderError(...) from original_exc``
    so callers can inspect the underlying transport error via __cause__.
    """

    def __init__(
        self,
        provider_name: str,
        detail: str,
        status_code: int | None = None,
    ):
        self.provider_name = provider_name
        self.detail = detail
        self.status_code = status_code
        msg = f"[{provider_name}] {detail}"
        if status_code is not None:
            msg = f"[{provider_name}] HTTP {status_code}: {detail}"
        super().__init__(msg)


class DimensionMismatchError(MimirEmbeddingsError):
    """Returned vector dimensions do not match expected dimensions."""

    def __init__(self, expected: int, actual: int, model: str):
        self.expected = expected
        self.actual = actual
        self.model = model
        super().__init__(
            f"Dimension mismatch for model '{model}': expected {expected}, got {actual}"
        )


class ConfigurationError(MimirEmbeddingsError):
    """Invalid or missing configuration."""