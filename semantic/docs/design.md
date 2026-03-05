# Embedding Generation Library — Architect Design Document

**Author**: Mimir Architecture Team
**Date**: 2026-03-04
**Status**: Draft
**Prerequisites**: Mimir Backend API v5.2.0, `mimir-client` v5.2.0 (PyPI)

---

## 1. Purpose

Mimir stores embeddings but does not generate them — by design the backend is model-agnostic. The `mimir-client` sends embeddings to the API but does not generate them. There is no shared mechanism for calling embedding providers, validating dimensions, or batching requests.

This library fills that single gap: **given text and an embedding type, return a vector.**

This is mechanism, not policy. The library does not prescribe how to ingest, how to retrieve, how to assemble context, or how to chunk. Applications compose this library with `mimir-client` to implement their own workflows.

---

## 2. System Context

```
┌──────────────────────────────────────────────┐
│            Application                        │
│  (ingestion scripts, RAG pipelines,           │
│   chat servers, analysis tools)               │
└──────┬──────────────────────┬────────────────┘
       │                      │
       │ vectors              │ artifacts, relations,
       │                      │ embeddings, search
       ▼                      ▼
┌──────────────┐    ┌──────────────────────────┐
│  Embedding   │    │     mimir-client          │
│  Library     │    │     (PyPI)                │
└──────┬───────┘    └──────────┬───────────────┘
       │                       │
       │ HTTP                  │ HTTP/REST
       ▼                       ▼
┌──────────────┐    ┌──────────────────────────┐
│  Embedding   │    │     Mimir Backend API     │
│  Providers   │    │                           │
│  (Ollama,    │    │                           │
│   OpenAI)    │    │                           │
└──────────────┘    └──────────────────────────┘
```

The embedding library and `mimir-client` are **peers**, not layered. The application uses both directly. The embedding library does not wrap or depend on `mimir-client` at runtime — it only needs `mimir-client` if the application wants dimension validation against registered embedding types.

---

## 3. What the Library Does

1. **Provider abstraction**: A uniform interface for generating embeddings from text, regardless of which provider (Ollama, OpenAI, etc.) is behind it.

2. **Batch support**: Generate embeddings for multiple texts in a single call, using the provider's native batch capabilities where available.

3. **Dimension validation**: Given an embedding type code, look up the expected dimensions (via `mimir-client`) and validate that the returned vector matches. This is optional — the library works without `mimir-client` if the caller knows the expected dimensions.

---

## 4. What the Library Does NOT Do

- Does not store embeddings (use `mimir-client` for that)
- Does not create artifacts or relations (use `mimir-client` for that)
- Does not search or retrieve (use `mimir-client` for that)
- Does not chunk content (the application decides what to embed)
- Does not assemble context or manage token budgets (application concern)
- Does not call LLMs for inference (application concern)
- Does not prescribe ingestion workflows (application concern)

---

## 5. Interface

The library exposes one primary interface:

**Embed text**: Given text and provider configuration, return a vector.

- Input: text (string), provider identifier
- Output: vector (list of floats), model name, token count
- Batch variant: list of texts in, list of vectors out

**Validate dimensions** (optional): Given a vector and an embedding type code, confirm the dimensions match what Mimir expects.

- Input: vector, embedding type code
- Output: pass or fail with expected vs actual dimensions
- Requires: `mimir-client` instance to look up embedding type metadata

---

## 6. Constraints

### C1: No Vendor SDK Dependencies

Provider implementations use raw HTTP calls (via `httpx`). No `openai` package, no `ollama` package. The embedding APIs are simple enough that thin HTTP wrappers are clearer, lighter, and avoid version conflicts.

### C2: Provider Independence

Adding a new provider does not require changes to existing providers or to applications using the library. Providers are pluggable.

### C3: No State

The library is stateless. It does not cache embeddings, track what has been embedded, or maintain any persistent state. Mimir is the single source of truth for stored embeddings.

### C4: Optional mimir-client Dependency

The library can generate embeddings without `mimir-client`. Dimension validation against Mimir's embedding type registry is an optional feature that requires a `mimir-client` instance. This keeps the library usable in contexts where Mimir is not involved (e.g., testing, standalone embedding generation).

---

## 7. Trade-offs

### T1: Raw HTTP vs Vendor SDKs

| Approach | Advantages | Disadvantages |
|----------|-----------|---------------|
| **Raw HTTP** (chosen) | No dependency conflicts; minimal footprint; full control; providers change APIs rarely | Must maintain HTTP integration code |
| **Vendor SDKs** | Slightly less code; SDK handles edge cases | Dependency version conflicts; heavyweight; SDK version churn |

**Decision**: Raw HTTP. The embedding APIs (Ollama `/api/embed`, OpenAI `/v1/embeddings`) are stable, simple JSON-in/JSON-out endpoints.

### T2: Peer to mimir-client vs Layer on Top

| Approach | Advantages | Disadvantages |
|----------|-----------|---------------|
| **Peer** (chosen) | Each can be used independently; no forced coupling; simpler dependency graph | Application must compose them manually |
| **Layer on top** | Convenience: embed-and-store in one call | Forces mimir-client dependency; library becomes policy (it decides to store) |

**Decision**: Peer. The application calls the embedding library to get vectors, then calls `mimir-client` to store them. This is two lines of code, not a hardship. An embed-and-store convenience belongs in the application, not in the mechanism library.

---

## 8. Relation to Other Documents

| Document | Relationship |
|----------|-------------|
| `docs/roadmap.md` | Priority 1 — this is the next work item |
| `docs/embedding-architecture-design.md` | Backend embedding type system this library validates against |
| `clients/python/docs/design.md` | Peer library (`mimir-client`) that applications compose with this |
| `semantic/docs/use-cases.md` | Business use cases that applications (not this library) will implement |

---

## 9. What This Document Does NOT Specify

- Class names, method signatures, module structure
- Provider-specific HTTP details
- Configuration format
- Error types
- Test strategy

The test: this design could be implemented in Python, Go, or TypeScript, and all implementations would satisfy the document.

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 0.1.0 | 2026-02-02 | Initial "semantic layer" design (over-scoped) |
| 0.2.0 | 2026-03-04 | Rewritten as architect-level design for semantic layer |
| 0.3.0 | 2026-03-04 | Reduced to embedding generation library only per mechanism-over-policy review |