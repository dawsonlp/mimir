# Mimir — Project Roadmap

**Last Updated**: 2026-03-04
**Current Version**: v5.2.0

---

## Completed Work

| Phase | Version | Summary |
|-------|---------|---------|
| Phase 1: Search Infrastructure | v2.x | Pagination, metadata filtering, parent-child hierarchy scoping |
| Phase 2: Deletion Infrastructure | v5.0.0 | Implemented then removed — replaced by append-only invariant with tenant-level FK CASCADE deletion |
| Phase 3: Search Unification | v3.0.0 | Unified `POST /search` with strategy inference; legacy endpoints removed |
| Phase 4: Graph Traversal Engine | v4.0.0 | Apache AGE Cypher engine; graph-scoped search; context service rewritten |
| Build Modernization | v5.0.0 | Poetry to uv + hatchling (PEP 621); CI modernized |
| Python Client Library | v5.2.0 | Async + sync clients with full API coverage; published to PyPI as `mimir-client` |
| Embedding Architecture | v5.x | Dynamic per-type vector tables in `mimir_vectors` schema; HNSW indexes per embedding type; dimension validation; provider metadata |

For historical design rationale on completed phases, see `docs/archive/`.

---

## Design Principles

Three principles govern all roadmap decisions:

| Principle | Meaning | Test |
|-----------|---------|------|
| **Mechanism, not policy** | Libraries provide capabilities; applications decide how to use them | "Does this component prescribe a workflow, or enable one?" |
| **KISS** | The smallest design that solves the real problem today | "Could a junior developer understand this?" |
| **DRY** | One place for every concept; don't re-wrap what already exists | "Am I duplicating something the backend or client already does?" |

Every proposed addition must pass all three tests before it earns a place on the roadmap.

---

## Forward Roadmap

### Priority 1 — Embedding Generation Library

**Problem**: Mimir stores embeddings but deliberately does not generate them (model-agnostic storage). The `mimir-client` sends embeddings but does not generate them. There is no shared mechanism for calling embedding providers, validating dimensions, or batching requests. Every consumer re-implements this independently.

**Scope**:
- Provider abstraction (Ollama, OpenAI — extensible to others)
- Batch embedding support
- Dimension validation against Mimir's embedding type metadata (via `mimir-client`)
- That's it. No ingestion policy, no retrieval policy, no context assembly.

**Principle**: Mechanism, not policy. "Give me text and an embedding type, I get back a vector." Applications compose this with `mimir-client` however they see fit.

**Design document**: `semantic/docs/design.md`

**Dependencies**: None. `mimir-client` and embedding type metadata are already available.

---

### Priority 2 — Validation Scenarios

**Problem**: No automated conformance test suite exercises the API end-to-end from a consumer's perspective. Integration tests exist but are developer-facing, not contract-facing.

**Scope**:
- Scripted end-to-end API validation scenarios
- Contract-level verification of all documented API behaviors
- Runnable as a standalone tool against any Mimir instance

**Principle**: Mechanism — verifiable contract tests.

**Design documents**: `tools/validation-scenarios/docs/requirements.md`, `tools/validation-scenarios/docs/api-assessment.md`

**Dependencies**: None.

---

### Priority 3 — Graph Engine Extensions (Phase 5)

**Problem**: The current graph engine handles traversal and scoped search. Advanced graph operations (pattern matching, path finding, subgraph extraction) are not yet exposed.

**Scope**:
- Match pattern queries (user-supplied Cypher patterns)
- Path finding endpoints (shortest path between artifacts)
- Subgraph extraction (return connected subgraph as JSON)
- Graph statistics endpoint (node/edge counts, density)

**Principle**: Mechanism — new query capabilities the backend exposes for any consumer.

**Design documents**: `docs/graph-search-design.md`, `docs/graph-engine-technical-design.md`

**Dependencies**: None.

---

### Priority 4 — ChatUI

**Problem**: No integrated chat interface with Mimir persistence exists. The echo server and protocol design provide a foundation, but the LLM-integrated chat server is not built.

**Scope**:
- Mimir-integrated chat server using `mimir-client` + embedding library
- Textual TUI chat client connected to real LLM backends

**Principle**: This is an **application**, not a library. It implements its own policy (how to ingest conversations, which retrieval strategy to use, how to assemble context) using `mimir-client` and the embedding library as mechanisms.

**Design documents**: `frontends/chatui/docs/requirements.md`, `frontends/chatui/middleware/conceptual_design.md`

**Dependencies**: Priority 1 (embedding generation library).

---

## What About Retrieval Strategies, Context Assembly, Ingestion Pipelines?

These are **application-level policy**, not library-level mechanism:

- **Retrieval strategy** (naive, parent-child, graph-aware): The Mimir backend already provides unified search with strategy inference, graph scoping, and hybrid modes via `POST /search`. The `mimir-client` exposes all of these. No wrapper library is needed.
- **Context assembly** (token budgeting, artifact selection): The Mimir backend already provides graph-based context retrieval via `GET /context/{artifact_id}`. Token budgeting for a specific LLM is an application concern.
- **Ingestion workflows** (chunk, store, relate, embed): How to decompose content into artifacts is domain-specific. A chat application chunks by turns. A documentation system chunks by sections. A code analysis tool chunks by functions. There is no generic "right answer" — this is policy.

If multiple applications converge on shared patterns, extract those patterns into utilities at that point. Not before.

---

## Long-Term Vision (from Requirements V2/V3)

These are not currently scheduled but represent the broader product direction:

- **V2 — Meta-workflow and Reflective Analysis**: Intent drift detection, redundancy detection, conversation meta-analysis
- **V3 — Multi-ontology and Synthesis Engine**: Ontology views, cross-intent synthesis, longitudinal insight

See `docs/requirements.md` for the full vision statement.