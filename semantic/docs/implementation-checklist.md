# Embedding Generation Library — Implementation Checklist

**Technical Design**: `semantic/docs/technical-design.md`
**Construction Order**: Per RULES.md — Domain objects first, tests alongside, infrastructure last

---

## Phase 1: Package Rename and Structure

- [x] Rename `semantic/src/mimir_semantic/` to `semantic/src/mimir_embeddings/`
- [x] Update `semantic/pyproject.toml` (name, packages, dependencies, dev deps)
- [x] Create `semantic/src/mimir_embeddings/providers/` directory with `__init__.py`
- [x] Verify `uv pip install -e ".[dev]"` succeeds

## Phase 2: Domain Objects (Steps 1-3)

- [x] `models.py`: `EmbeddingResult` frozen dataclass
- [x] `exceptions.py`: `MimirEmbeddingsError`, `ProviderError`, `DimensionMismatchError`, `ConfigurationError`
- [x] `validation.py`: `validate_dimensions()` utility
- [x] `tests/unit/test_models.py`: EmbeddingResult construction, immutability
- [x] `tests/unit/test_exceptions.py`: Exception attributes, inheritance, chaining
- [x] `tests/unit/test_validation.py`: Pass/fail cases, property test with hypothesis

## Phase 3: Provider ABC (Step 4)

- [x] `providers/base.py`: `EmbeddingProvider` ABC with `generate()`, `generate_batch()`, context manager

## Phase 4: Provider Implementations (Steps 5-6)

- [x] `config.py`: `OllamaConfig`, `OpenAIConfig` (pydantic-settings)
- [x] `providers/ollama.py`: `OllamaProvider` with httpx
- [x] `providers/openai.py`: `OpenAIProvider` with httpx
- [x] `tests/unit/test_config.py`: Env loading, defaults, validation, missing required
- [x] `tests/unit/test_ollama.py`: Mocked HTTP — outcomes and error paths
- [x] `tests/unit/test_openai.py`: Mocked HTTP — outcomes, error paths, batch ordering

## Phase 5: Public API and Integration (Steps 8-10)

- [x] `__init__.py`: Public API exports
- [x] `providers/__init__.py`: Provider re-exports
- [x] `tests/integration/test_ollama_live.py`: Round-trip with running Ollama
- [x] Update `README.md`
- [x] Final verification: `uv pip install -e ".[dev]"` and `pytest tests/unit -v` — 48 passed
- [x] Integration tests: `pytest tests/integration -v` — 4 passed