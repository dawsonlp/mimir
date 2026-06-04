# Embedding Generation Library — Technical Design

**Status**: Draft
**Date**: 2026-03-05
**Author**: Lead Senior Engineer
**Implements**: `semantic/docs/design.md`
**Depends on**: Mimir Backend API v5.5.1, `mimir-client` v5.5.1 (peer, not import dependency)
**Status**: Implemented as `mimir-embeddings` package v0.1.0.

---

## 1. Objective

Bridge the architect design (`semantic/docs/design.md`) to implementation for the Embedding Generation Library. This document specifies library and framework choices, data structures, provider integration patterns, error handling, and testing strategy. The implementing engineer makes all final coding decisions within these constraints.

The library fills one gap: **given text, return a vector from an external embedding provider.** It does not prescribe ingestion, retrieval, context assembly, or chunking — those are application-level policy.

---

## 2. Decisions

### D1. Package Name — Rename to `mimir-embeddings`

**Decision**: Rename from `mimir-semantic` / `mimir_semantic` to `mimir-embeddings` / `mimir_embeddings`.

**Rationale**: The library scope is strictly embedding generation. The name `mimir-semantic` implies broader semantic capabilities that do not exist and are not planned. `mimir-embeddings` communicates purpose immediately and follows KISS. The existing stubs are empty — zero migration cost.

**Impact**: Rename `semantic/src/mimir_semantic/` to `semantic/src/mimir_embeddings/`, update `pyproject.toml` name and `[tool.hatch.build.targets.wheel]` packages. The workspace directory `semantic/` does not change.

**Environment variable prefix**: `MIMIR_EMBEDDINGS_` (per STANDARDS.md service prefix convention).

### D2. Provider Interface — Async ABC with `generate()` and `generate_batch()`

**Decision**: Define an `EmbeddingProvider` ABC with two async methods. Method names are `generate` and `generate_batch` — not `embed_text` / `embed_batch` as in the backend. The backend names leak implementation; "generate" describes the action from the caller's perspective.

The ABC is deliberately minimal:

```python
class EmbeddingProvider(ABC):
    @abstractmethod
    async def generate(self, text: str) -> EmbeddingResult: ...

    @abstractmethod
    async def generate_batch(self, texts: list[str]) -> list[EmbeddingResult]: ...

    @property
    @abstractmethod
    def dimensions(self) -> int: ...

    @property
    @abstractmethod
    def model_name(self) -> str: ...
```

Key differences from the backend's `EmbeddingProvider`:

| Aspect | Backend provider | Library provider |
|--------|-----------------|-----------------|
| Model selection | `model` parameter on every call | Fixed at construction (one provider instance = one model) |
| Model listing | `list_models()`, `get_model_info()` | Not included — discovery is not embedding generation |
| Registry | Global registry with `register_provider()` | No registry — applications compose providers directly |
| Sync/async | Mixed | Async-only (constraint C2) |

**Rationale for fixed model**: Embedding providers are configured once per embedding type. An application generating embeddings for `text-embedding-3-small` creates one provider instance. This eliminates per-call model validation and simplifies the interface. Applications needing multiple models create multiple provider instances.

### D3. Batch Implementation — Provider-native Where Supported

**Decision**:

- **OpenAI**: Native batch. The OpenAI embeddings API accepts a list of inputs in a single request. `OpenAIProvider.generate_batch()` sends all texts in one HTTP call and returns results in input order.
- **Ollama**: Sequential iteration. The Ollama `/api/embed` endpoint (stable releases) accepts a single input string. `OllamaProvider.generate_batch()` calls `generate()` for each text sequentially. Concurrency is not added — Ollama processes one embedding at a time on the GPU, so concurrent requests queue server-side with added connection overhead.

The ABC provides no default implementation. Each provider implements `generate_batch()` explicitly, making the batching strategy visible and testable.

### D4. Configuration — Pydantic-settings with Constructor Override

**Decision**: Use `pydantic-settings` for environment-based configuration. Each provider has a settings class that loads from environment variables. Provider constructors also accept explicit parameters that override settings.

```python
class OllamaConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MIMIR_EMBEDDINGS_OLLAMA_")

    base_url: str = "http://localhost:11434"
    model: str = "nomic-embed-text"
    dimensions: int = 768
    timeout: float = 30.0


class OpenAIConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MIMIR_EMBEDDINGS_OPENAI_")

    api_key: SecretStr  # No default — must be provided
    base_url: str = "https://api.openai.com/v1"
    model: str = "text-embedding-3-small"
    dimensions: int = 1536
    timeout: float = 30.0
```

**Usage patterns**:

```python
# From environment (12-factor)
provider = OllamaProvider(OllamaConfig())

# Explicit construction (testing, scripts)
provider = OllamaProvider(OllamaConfig(model="mxbai-embed-large", dimensions=1024))
```

**Rationale**: Pydantic-settings is already a project standard (STANDARDS.md). Constructor override enables testing without environment manipulation. Secret values use `SecretStr` to prevent accidental logging.

### D5. Dimension Validation — Automatic on Every Result

**Decision**: Every `generate()` and `generate_batch()` call validates that the returned vector length matches `self.dimensions`. Validation is not optional and cannot be skipped. This implements constraint C3 (fail fast on dimension mismatch).

```python
# Inside provider base or each implementation
if len(embedding) != self.dimensions:
    raise DimensionMismatchError(
        expected=self.dimensions,
        actual=len(embedding),
        model=self.model_name,
    )
```

A standalone utility function is also exposed for callers who need ad-hoc validation (e.g., validating vectors from other sources before storing via `mimir-client`):

```python
def validate_dimensions(vector: list[float], expected: int) -> None:
    """Raise DimensionMismatchError if len(vector) != expected."""
```

**Rationale**: The library is a peer to `mimir-client` (constraint C4) — it does not import or call `mimir-client` to look up expected dimensions. The provider's configured `dimensions` value is the source of truth. Applications are responsible for ensuring their provider config matches their Mimir embedding type configuration.

### D6. Exception Hierarchy

**Decision**: Flat hierarchy rooted in a single base exception. Three concrete exceptions cover all failure modes.

```python
class MimirEmbeddingsError(Exception):
    """Base exception for all mimir-embeddings errors."""

class ProviderError(MimirEmbeddingsError):
    """Provider HTTP call failed (network, auth, rate limit, server error)."""
    # Attributes: provider_name, status_code (optional), detail

class DimensionMismatchError(MimirEmbeddingsError):
    """Returned vector dimensions do not match expected dimensions."""
    # Attributes: expected, actual, model

class ConfigurationError(MimirEmbeddingsError):
    """Invalid or missing configuration (e.g., no API key for OpenAI)."""
```

**Rationale**: Three exceptions cover the three failure categories: network/provider failures, data validation failures, and setup failures. No deeper hierarchy — KISS. `ProviderError` wraps the underlying `httpx` exception as `__cause__` via `raise ProviderError(...) from exc` so callers can inspect the original error when needed.

### D7. tiktoken Dependency — Remove

**Decision**: Remove `tiktoken` from dependencies. Token budgeting was removed from library scope (it is application-level policy). Token counts are available from provider API responses:

- **Ollama**: Response includes `total_duration` but not token count in current stable API. Token count will be `None`.
- **OpenAI**: Response includes `usage.total_tokens`. Token count is populated.

`EmbeddingResult.token_count` remains as `int | None`. Applications that need pre-call token estimation can add `tiktoken` as their own dependency.

**Rationale**: YAGNI. The library generates embeddings; it does not budget tokens. Removing `tiktoken` eliminates a 5MB+ transitive dependency (includes compiled Rust tokenizers) that would serve no function in the library.

### D8. Test Strategy

**Decision**: Three test tiers, organized by confidence level rather than by mock vs real.

**Integration tests** (`tests/integration/`) — primary confidence:
- Require a running Ollama instance with `nomic-embed-text` model pulled
- Test the actual promise: text in, correctly-dimensioned vector out
- Marked with `@pytest.mark.integration`, skip when Ollama unavailable

**Unit tests** (`tests/unit/`) — error paths and OpenAI:
- Mock HTTP responses using `respx` (httpx mock library)
- Assert caller-visible outcomes (correct results, correct exceptions with diagnosable attributes), not request construction details
- Cover error paths that cannot be triggered via integration: auth failure, rate limiting, malformed response

**Property tests** (within unit tests) — invariant verification:
- Use `hypothesis` to verify dimension conservation, batch count conservation, batch ordering, and validation completeness
- Catch edge cases that example-based tests miss

**No OpenAI integration tests**: OpenAI tests would require API keys and incur costs. Provider logic is validated via unit tests with mocked responses matching the documented API format.

### D9. Construction Order

Per RULES.md, implementation proceeds in this order:

1. **Domain objects**: `EmbeddingResult` dataclass, exception classes
2. **Domain tests**: Test `EmbeddingResult` construction, `validate_dimensions()`, exception attributes
3. **Provider ABC**: `EmbeddingProvider` abstract class
4. **Ollama provider**: Implementation with httpx
5. **OpenAI provider**: Implementation with httpx
6. **Provider unit tests**: Mock HTTP responses with `respx`, test all error paths
7. **Configuration**: Pydantic-settings classes for each provider
8. **Integration tests**: Ollama round-trip tests
9. **Package metadata**: Update `pyproject.toml`, `__init__.py` exports, README

---

## 3. Module Structure

```
semantic/
├── src/
│   └── mimir_embeddings/
│       ├── __init__.py            # Public API: re-exports provider classes, result, exceptions
│       ├── models.py              # EmbeddingResult dataclass
│       ├── exceptions.py          # Exception hierarchy
│       ├── validation.py          # validate_dimensions() utility
│       ├── config.py              # OllamaConfig, OpenAIConfig (pydantic-settings)
│       └── providers/
│           ├── __init__.py        # Re-exports provider classes
│           ├── base.py            # EmbeddingProvider ABC
│           ├── ollama.py          # OllamaProvider
│           └── openai.py         # OpenAIProvider
├── tests/
│   ├── conftest.py                # Shared fixtures
│   ├── unit/
│   │   ├── test_models.py         # EmbeddingResult, validation
│   │   ├── test_ollama.py         # OllamaProvider with mocked HTTP
│   │   ├── test_openai.py         # OpenAIProvider with mocked HTTP
│   │   └── test_config.py         # Configuration loading
│   └── integration/
│       └── test_ollama_live.py    # Round-trip with running Ollama
├── pyproject.toml
├── README.md
└── docs/
    ├── design.md                  # Architect design (exists)
    └── technical-design.md        # This document
```

**Package boundary**: Only symbols exported from `mimir_embeddings/__init__.py` are public API. Internal module paths are implementation details.

---

## 4. Domain Objects

### 4.1 EmbeddingResult

```python
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class EmbeddingResult:
    """Immutable result of a single embedding generation call."""

    embedding: list[float]
    model: str
    dimensions: int
    token_count: int | None = None
```

**Design choices**:
- `frozen=True` — immutability by default (per RULES.md core principles)
- `slots=True` — reduced memory footprint for batch results
- `dimensions` stored explicitly rather than computed via `len(embedding)` — avoids repeated computation and makes the value inspectable without accessing the vector
- `token_count` is `None` when the provider does not report it (Ollama)

The `dimensions` field is set by the provider after validation. If validation passes, `dimensions == len(embedding)` is guaranteed.

### 4.2 Validation Utility

```python
def validate_dimensions(vector: list[float], expected: int) -> None:
    """Raise DimensionMismatchError if vector length does not match expected.

    Providers call this internally on every result. Exposed publicly for
    callers who need to validate vectors from other sources.
    """
    actual = len(vector)
    if actual != expected:
        raise DimensionMismatchError(expected=expected, actual=actual, model="unknown")
```

---

## 5. Provider Interface

### 5.1 EmbeddingProvider ABC

```python
from abc import ABC, abstractmethod


class EmbeddingProvider(ABC):
    """Base class for embedding providers.

    Each instance is bound to a single model. Applications needing
    multiple models create multiple provider instances.
    """

    @abstractmethod
    async def generate(self, text: str) -> EmbeddingResult:
        """Generate an embedding for a single text.

        Raises:
            ProviderError: HTTP call failed.
            DimensionMismatchError: Returned vector has wrong dimensions.
        """

    @abstractmethod
    async def generate_batch(self, texts: list[str]) -> list[EmbeddingResult]:
        """Generate embeddings for multiple texts.

        Returns results in the same order as inputs.

        Raises:
            ProviderError: HTTP call failed.
            DimensionMismatchError: Any returned vector has wrong dimensions.
        """

    @property
    @abstractmethod
    def dimensions(self) -> int:
        """Expected embedding dimensions for this provider's model."""

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Model identifier string."""

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        await self.close()

    async def close(self) -> None:
        """Release HTTP client resources. Override in implementations."""
```

**Context manager support**: Providers own an `httpx.AsyncClient` internally. The async context manager pattern ensures the client is closed cleanly. This follows the same pattern as `mimir-client`.

### 5.2 OllamaProvider

**HTTP integration**:
- Endpoint: `POST {base_url}/api/embed`
- Request body: `{"model": "<model>", "input": "<text>"}`
- Response body: `{"embeddings": [[...]], "total_duration": ...}`

**Implementation notes**:
- Creates `httpx.AsyncClient` with configured `base_url` and `timeout`
- Parses response, extracts first embedding from the `embeddings` array
- Validates dimensions, constructs `EmbeddingResult` with `token_count=None`
- `generate_batch()` iterates sequentially — no concurrency (see D3)
- On HTTP error: wraps `httpx.HTTPStatusError` in `ProviderError`
- On connection error: wraps `httpx.ConnectError` in `ProviderError`

**Error mapping**:

| httpx exception | Library exception | Detail |
|----------------|-------------------|--------|
| `ConnectError` | `ProviderError` | Cannot reach Ollama at configured URL |
| `HTTPStatusError` 404 | `ProviderError` | Model not found / not pulled |
| `HTTPStatusError` 5xx | `ProviderError` | Ollama server error |
| `TimeoutException` | `ProviderError` | Request exceeded configured timeout |

### 5.3 OpenAIProvider

**HTTP integration**:
- Endpoint: `POST {base_url}/embeddings`
- Request headers: `Authorization: Bearer {api_key}`
- Request body: `{"model": "<model>", "input": "<text_or_list>", "dimensions": <n>}`
- Response body: `{"data": [{"embedding": [...], "index": 0}], "usage": {"total_tokens": N}}`

**Implementation notes**:
- Creates `httpx.AsyncClient` with configured `base_url` and `timeout`
- Sets `Authorization` header from `api_key` config (extracted from `SecretStr`)
- For `generate()`: sends `input` as a single string
- For `generate_batch()`: sends `input` as a list of strings — native batching in one HTTP call
- Sorts response `data` by `index` to guarantee input-order results
- Extracts `usage.total_tokens` for `token_count` (divided evenly across batch results when batching, or exact when single)
- Validates dimensions on each result
- On 401: `ProviderError` with detail indicating authentication failure
- On 429: `ProviderError` with detail indicating rate limiting

**Error mapping**:

| httpx exception / status | Library exception | Detail |
|-------------------------|-------------------|--------|
| `ConnectError` | `ProviderError` | Cannot reach OpenAI API |
| `HTTPStatusError` 401 | `ProviderError` | Invalid API key |
| `HTTPStatusError` 429 | `ProviderError` | Rate limited |
| `HTTPStatusError` 5xx | `ProviderError` | OpenAI server error |
| `TimeoutException` | `ProviderError` | Request exceeded configured timeout |

---

## 6. Configuration

### 6.1 Environment Variables

| Variable | Provider | Default | Required |
|----------|----------|---------|----------|
| `MIMIR_EMBEDDINGS_OLLAMA_BASE_URL` | Ollama | `http://localhost:11434` | No |
| `MIMIR_EMBEDDINGS_OLLAMA_MODEL` | Ollama | `nomic-embed-text` | No |
| `MIMIR_EMBEDDINGS_OLLAMA_DIMENSIONS` | Ollama | `768` | No |
| `MIMIR_EMBEDDINGS_OLLAMA_TIMEOUT` | Ollama | `30.0` | No |
| `MIMIR_EMBEDDINGS_OPENAI_API_KEY` | OpenAI | — | Yes |
| `MIMIR_EMBEDDINGS_OPENAI_BASE_URL` | OpenAI | `https://api.openai.com/v1` | No |
| `MIMIR_EMBEDDINGS_OPENAI_MODEL` | OpenAI | `text-embedding-3-small` | No |
| `MIMIR_EMBEDDINGS_OPENAI_DIMENSIONS` | OpenAI | `1536` | No |
| `MIMIR_EMBEDDINGS_OPENAI_TIMEOUT` | OpenAI | `30.0` | No |

### 6.2 Configuration Validation

Pydantic-settings validates types and required fields at construction time. `ConfigurationError` is raised (not pydantic's `ValidationError`) when configuration is invalid, providing a consistent exception interface:

```python
try:
    config = OpenAIConfig()
except ValidationError as exc:
    raise ConfigurationError(str(exc)) from exc
```

This translation happens in a factory function, not in the provider constructor, so that callers who construct configs manually get pydantic's native validation.

---

## 7. Error Handling Strategy

### 7.1 Principles

- **Fail fast**: Dimension mismatches raise immediately, never return bad data
- **Wrap, don't leak**: All `httpx` exceptions are wrapped in `ProviderError` — callers depend on library exceptions, not httpx internals
- **Preserve cause**: `raise ProviderError(...) from exc` preserves the original exception for debugging
- **No retry in the library**: Retry is application-level policy. The library reports failures; applications decide retry strategy

### 7.2 Error Flow

```
Application calls provider.generate("text")
  │
  ├── httpx raises ConnectError
  │   └── Wrapped in ProviderError(provider_name="ollama", detail="Connection refused")
  │
  ├── httpx raises HTTPStatusError (4xx/5xx)
  │   └── Wrapped in ProviderError(provider_name="ollama", status_code=404, detail="Model not found")
  │
  ├── httpx raises TimeoutException
  │   └── Wrapped in ProviderError(provider_name="ollama", detail="Request timed out")
  │
  ├── Response parsed successfully but len(embedding) != expected
  │   └── DimensionMismatchError(expected=768, actual=512, model="nomic-embed-text")
  │
  └── Response parsed successfully and dimensions match
      └── Returns EmbeddingResult
```

---

## 8. Testing Strategy

### 8.1 Testing Philosophy Applied

This library's tests follow the RULES.md testing principles:

**Test outcomes, not code.** Tests assert what the library promises to callers — "given text, return a correctly-dimensioned vector" and "on failure, raise a library exception with diagnosable context." Tests do not assert how requests are constructed or what internal methods are called. If the provider switches from one HTTP endpoint to another but the outcome is identical, tests should still pass.

**Favor contact with reality.** Integration tests against a running Ollama instance are the strongest tests this library has. Unit tests with mocked HTTP are a necessary supplement for error paths and for OpenAI (where real calls cost money), but they are not the primary confidence source. When both a unit test and an integration test cover the same outcome, the integration test is authoritative.

**Concentrate effort where risk lives.** The real risks in this library are:

| Risk | Consequence | Test investment |
|------|------------|-----------------|
| Wrong-dimension vectors stored in Mimir | Corrupted search results, silent data quality degradation | Heavy — dimension validation tested at every level |
| Provider errors leaking as httpx exceptions | Callers write fragile error handling tied to transport library | Medium — verify library exceptions wrap all failure modes |
| Batch results in wrong order | Embeddings stored against wrong artifacts | Medium — property test for ordering invariant |
| Configuration missing or wrong type | Runtime crash on first call instead of at startup | Light — pydantic-settings handles most of this |

**Keep the system explainable under failure.** Every exception carries enough context to diagnose the problem without a debugger: `ProviderError` includes `provider_name`, `status_code`, and `detail`; `DimensionMismatchError` includes `expected`, `actual`, and `model`. Tests assert these attributes are populated and meaningful.

### 8.2 Integration Tests (Primary Confidence)

**Prerequisite**: Running Ollama instance with `nomic-embed-text` model.

Integration tests are the most valuable tests in this library. They prove the actual promise: text goes in, correctly-dimensioned vector comes out.

**Skip mechanism**:

```python
import pytest
import httpx

pytestmark = pytest.mark.integration


def ollama_available():
    """Check if Ollama is reachable."""
    try:
        httpx.get("http://localhost:11434/api/tags", timeout=2.0)
        return True
    except (httpx.ConnectError, httpx.TimeoutException):
        return False


skip_no_ollama = pytest.mark.skipif(
    not ollama_available(), reason="Ollama not available"
)
```

**Outcomes tested**:
- Single text produces an `EmbeddingResult` with `len(embedding) == dimensions`
- Batch of N texts produces N results, each with correct dimensions
- Non-existent model raises `ProviderError` (not httpx exception)
- Result fields (`model`, `dimensions`) match provider configuration

### 8.3 Unit Tests (Error Paths and OpenAI)

**Tool**: `pytest` + `respx` (httpx mock library, dev dependency)

Unit tests cover outcomes that cannot be tested via integration: error paths, OpenAI provider behavior (no free API), and edge cases in response parsing. Mocks simulate provider HTTP responses; tests assert caller-visible outcomes, not request internals.

**Outcome-focused test examples (clarifies methodology, not full implementation)**:

```python
@pytest.fixture
def ollama_provider():
    config = OllamaConfig(base_url="http://test:11434", model="test-model", dimensions=3)
    return OllamaProvider(config)


async def test_generate_valid_text_returns_correct_result(respx_mock, ollama_provider):
    """Promise: given text, return an EmbeddingResult with matching dimensions."""
    respx_mock.post("http://test:11434/api/embed").respond(
        json={"embeddings": [[0.1, 0.2, 0.3]]}
    )
    result = await ollama_provider.generate("hello")
    assert len(result.embedding) == 3
    assert result.dimensions == 3
    assert result.model == "test-model"


async def test_generate_wrong_dimensions_raises_with_context(respx_mock, ollama_provider):
    """Promise: dimension mismatch is caught immediately with diagnosable error."""
    respx_mock.post("http://test:11434/api/embed").respond(
        json={"embeddings": [[0.1, 0.2]]}
    )
    with pytest.raises(DimensionMismatchError) as exc_info:
        await ollama_provider.generate("hello")
    assert exc_info.value.expected == 3
    assert exc_info.value.actual == 2
    assert exc_info.value.model == "test-model"


async def test_generate_unreachable_provider_raises_provider_error(respx_mock, ollama_provider):
    """Promise: transport failures are wrapped in ProviderError, not leaked."""
    respx_mock.post("http://test:11434/api/embed").mock(
        side_effect=httpx.ConnectError("Connection refused")
    )
    with pytest.raises(ProviderError) as exc_info:
        await ollama_provider.generate("hello")
    assert exc_info.value.provider_name == "ollama"
    assert "Connection refused" in exc_info.value.detail
```

### 8.4 Property Tests

Property-based tests (using `hypothesis`) verify invariants that hold across all inputs, not just example cases. These catch edge cases that example tests miss.

**Properties to verify**:

| Property | Invariant | Applies to |
|----------|-----------|------------|
| **Dimension conservation** | `len(result.embedding) == provider.dimensions` for any text that succeeds | All providers |
| **Batch count conservation** | `len(results) == len(inputs)` for any batch that succeeds | All providers |
| **Batch ordering** | `results[i]` corresponds to `inputs[i]` — verified by embedding distinct texts and checking results are distinguishable | OpenAI batch |
| **Validation completeness** | `validate_dimensions(vec, n)` raises iff `len(vec) != n` for arbitrary vectors and dimension values | `validate_dimensions()` |

**Example** (clarifies approach):

```python
from hypothesis import given, strategies as st


@given(st.lists(st.floats(allow_nan=False, allow_infinity=False), min_size=1, max_size=4096))
def test_validate_dimensions_raises_iff_length_mismatches(vector):
    expected = len(vector)
    validate_dimensions(vector, expected)  # Should not raise

    if len(vector) > 0:
        with pytest.raises(DimensionMismatchError):
            validate_dimensions(vector, expected + 1)
```

Property tests for providers use mocked HTTP (respx) that returns vectors of the configured dimension. The property under test is the invariant, not the mock.

### 8.5 Test Naming

Per STANDARDS.md: `test_<action>_<condition>_<expected>`

Examples:
- `test_generate_valid_text_returns_correct_result`
- `test_generate_unreachable_provider_raises_provider_error`
- `test_generate_wrong_dimensions_raises_with_context`
- `test_generate_batch_n_inputs_returns_n_results`
- `test_validate_dimensions_mismatched_length_raises`

---

## 9. Dependencies

### Runtime

| Package | Version | Purpose |
|---------|---------|---------|
| `httpx` | `>=0.27` | HTTP client for provider API calls |
| `pydantic-settings` | `>=2.0` | Environment-based configuration |
| `pydantic` | `>=2.0` | Transitive via pydantic-settings |

### Dev

| Package | Version | Purpose |
|---------|---------|---------|
| `pytest` | latest | Test runner |
| `pytest-asyncio` | latest | Async test support |
| `respx` | latest | httpx request mocking |
| `ruff` | latest | Linting and formatting |
| `mypy` | latest | Type checking |
| `hypothesis` | latest | Property-based testing |

### Removed

| Package | Reason |
|---------|--------|
| `tiktoken` | Token budgeting not in library scope (D7). Token counts come from API responses. |

---

## 10. Public API Surface

The `__init__.py` exports define the library's public contract:

```python
from mimir_embeddings.models import EmbeddingResult
from mimir_embeddings.providers.base import EmbeddingProvider
from mimir_embeddings.providers.ollama import OllamaProvider
from mimir_embeddings.providers.openai import OpenAIProvider
from mimir_embeddings.config import OllamaConfig, OpenAIConfig
from mimir_embeddings.exceptions import (
    MimirEmbeddingsError,
    ProviderError,
    DimensionMismatchError,
    ConfigurationError,
)
from mimir_embeddings.validation import validate_dimensions
```

**Usage example** (clarifies integration pattern, not library internals):

```python
from mimir_embeddings import OllamaProvider, OllamaConfig
from mimir_client import MimirClient

async def ingest_document(text: str, artifact_id: UUID, tenant_id: int):
    """Application code — NOT part of the library."""
    async with OllamaProvider(OllamaConfig()) as provider:
        result = await provider.generate(text)

    async with MimirClient(api_url="http://localhost:38000", tenant_id=tenant_id) as client:
        await client.create_embedding(
            artifact_id=artifact_id,
            embedding_type_code="nomic-embed-text",
            embedding=result.embedding,
        )
```

This demonstrates the peer relationship (constraint C4): the application composes both libraries. Neither imports the other.

---

## 11. Relation to Backend Providers

The backend's `embedding_providers/` module (in `backend/src/mimir/services/`) contains a working implementation of the same provider pattern. Trade-off T1 in the architect design accepts this duplication.

**Key differences**:

| Aspect | Backend providers | Library providers |
|--------|------------------|-------------------|
| Scope | Internal service, coupled to backend lifecycle | Standalone PyPI package |
| Model | Per-call model parameter | Per-instance model (fixed at construction) |
| Registry | Global mutable registry | No registry |
| Configuration | Backend settings object | Independent pydantic-settings |
| Dimension validation | Not performed | Automatic on every result |

The implementing engineer should study `backend/src/mimir/services/embedding_providers/ollama_provider.py` and `openai_provider.py` for proven HTTP integration patterns (request format, response parsing, error handling). The library implementations will follow the same HTTP patterns but with the cleaner interface defined in this document.

---

## 12. Construction Order

Per RULES.md, implementation proceeds in this strict order. Each step is independently testable before the next step begins.

| Step | Deliverable | Test |
|------|------------|------|
| 1 | `models.py`: `EmbeddingResult` dataclass | Unit: construction, frozen immutability, slots |
| 2 | `exceptions.py`: Exception hierarchy | Unit: instantiation, attributes, inheritance |
| 3 | `validation.py`: `validate_dimensions()` | Unit: pass and fail cases |
| 4 | `providers/base.py`: `EmbeddingProvider` ABC | (Not directly tested — abstract) |
| 5 | `providers/ollama.py`: `OllamaProvider` | Unit: mocked HTTP via `respx` |
| 6 | `providers/openai.py`: `OpenAIProvider` | Unit: mocked HTTP via `respx` |
| 7 | `config.py`: `OllamaConfig`, `OpenAIConfig` | Unit: env loading, defaults, validation |
| 8 | `__init__.py`: Public API exports | Verify import paths |
| 9 | `tests/integration/test_ollama_live.py` | Integration: requires running Ollama |
| 10 | `pyproject.toml` updates, `README.md` | Package builds and installs cleanly |

---

## 13. Acceptance Criteria

The library is complete when:

1. `OllamaProvider` generates embeddings from a running Ollama instance and returns `EmbeddingResult` with correct dimensions
2. `OpenAIProvider` generates embeddings using mocked HTTP responses (unit tests verify request/response handling)
3. Dimension mismatches raise `DimensionMismatchError` immediately — no silent failures
4. All `httpx` exceptions are wrapped in `ProviderError` — no httpx types leak to callers
5. Configuration loads from environment variables with `MIMIR_EMBEDDINGS_` prefix
6. `tiktoken` is not in the dependency list
7. Unit tests pass with no I/O (all HTTP mocked)
8. Integration tests pass with a running Ollama instance (skipped when unavailable)
9. Package installs cleanly: `uv pip install -e ".[dev]"` from the `semantic/` directory
10. The library does NOT import `mimir-client` — peer relationship verified by inspection
