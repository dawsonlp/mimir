# Prompt: Senior Engineer — Embedding Generation Library Technical Design

You are the lead senior engineer for Mimir. Your task is to write `semantic/docs/technical-design.md` for the Embedding Generation Library (Roadmap Priority 1).

## Your Responsibilities (from RULES.md)

A technical design document bridges architecture to implementation. You choose:
- Library and framework choices with rationale
- Data structures and algorithms
- Integration patterns with external systems
- Error handling strategies
- Testing strategy specific to the implementation
- Code snippets that clarify methodology or best practices

You do NOT re-state business requirements or architectural rationale — those exist in other documents.

## Required Reading

Read these documents in order before writing the technical design:

1. **Global rules**: Read the `.clinerules/` files (RULES.md, STANDARDS.md, python_development.md, TOOLS.md) to understand project standards, construction order, testing philosophy, and Python conventions.

2. **Architect design** (your primary input): `semantic/docs/design.md` — defines the library's scope, constraints, interface, and trade-offs. The library provides: provider abstraction, batch support, dimension validation. It is a peer to `mimir-client`, not a layer on top.

3. **Roadmap**: `docs/roadmap.md` — confirms this is Priority 1 and states the three design principles (Mechanism not Policy, KISS, DRY).

4. **Backend embedding provider pattern**: `backend/src/mimir/services/embedding_providers/` — contains `base.py` (EmbeddingProvider ABC, EmbeddingResult dataclass), `ollama_provider.py`, and `openai_provider.py`. Study this pattern — the architect design says to reuse it with modifications for async and batch support.

5. **Existing stubs**: `semantic/src/mimir_semantic/` — contains `__init__.py`, `client.py`, `config.py`, `exceptions.py` (all empty stubs). `semantic/pyproject.toml` — current dependencies include `httpx>=0.27` and `tiktoken>=0.9`.

6. **mimir-client API surface**: `clients/python/src/mimir_client/client.py` — understand `get_embedding_type()` and `create_embedding()` methods that applications will use alongside this library. The library itself does NOT depend on `mimir-client` at runtime (constraint C4).

7. **Embedding type metadata**: `docs/embedding-architecture-design.md` — understand what fields embedding types have (code, provider, dimensions, distance_metric, etc.) so the dimension validation feature can reference the right metadata.

## Scope — What to Design

The library does exactly three things:

1. **Provider abstraction**: ABC with implementations for Ollama and OpenAI. Async-first with sync wrappers. Uses raw `httpx` — no vendor SDKs (constraint C1).

2. **Batch support**: Generate embeddings for multiple texts using provider-native batch capabilities where available.

3. **Dimension validation**: Optional validation that a returned vector matches expected dimensions. Can work standalone (caller provides expected dimensions) or with `mimir-client` (look up dimensions from embedding type registry).

That's it. No ingestion, no retrieval, no context assembly, no chunking, no token budgeting.

## Decisions You Must Make

- Package name and module structure (the existing package is `mimir-semantic` / `mimir_semantic` — decide whether to keep this name or rename to something more accurate like `mimir-embeddings` / `mimir_embeddings`)
- Provider ABC: method signatures, async vs sync patterns, error handling
- How Ollama and OpenAI providers implement batch (Ollama has native batch; OpenAI accepts list input)
- Configuration approach (pydantic-settings? simple dataclass? constructor parameters only?)
- How dimension validation works when `mimir-client` is not available vs when it is
- Exception hierarchy (what errors can occur and how they're typed)
- Whether `tiktoken` remains a dependency (the architect design removed token budgeting from scope — is tiktoken still needed for anything?)
- Test strategy: what unit tests (pure, no I/O), what integration tests (require running Ollama)
- Construction order per RULES.md (domain objects first, tests, then infrastructure)

## Deliverable

Write `semantic/docs/technical-design.md` following the format established by other technical designs in the project (see `docs/graph-engine-technical-design.md` or `docs/unified-search-technical-design.md` for examples of the expected level of detail).

## Principles to Follow

- **Mechanism, not policy**: This library provides "give me text, get back a vector." It does not decide what to do with the vector.
- **KISS**: The smallest design that works. If a feature isn't needed by the three use cases (provider abstraction, batch, dimension validation), don't include it.
- **DRY**: Don't re-wrap what `mimir-client` already does. Don't duplicate the backend's provider implementations — adapt them.