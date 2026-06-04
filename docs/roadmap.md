# Mimir — Project Roadmap

**Last Updated**: 2026-06-04
**Current Version**: v5.5.1

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
| Client Tenant Shortname Migration | v5.3.0 | `tenant: str` shortname is the primary client identifier; `tenant_id` remains deprecated until v6.0.0 |
| Embedding Architecture | v5.x | Dynamic per-type vector tables in `mimir_vectors` schema; HNSW indexes per embedding type; dimension validation; provider metadata |
| UUIDv7 Rollout | v5.4.0 | Client-generated UUIDv7 support and release alignment |
| Change Outbox | v5.5.0 | Transactional outbox, retained replay ledger, and Kafka publisher for artifact, relation, and embedding creates |
| Tenant Metadata JSONB Fix | v5.5.1 | Tenant create/update adapts metadata dictionaries as JSONB values before passing them to psycopg |
| Embedding Generation Library | package v0.1.0 | Standalone `mimir-embeddings` provider abstraction for Ollama/OpenAI, batching, and dimension validation |

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

### Priority 1 — Validation Scenarios v5 Contract Tool

**Problem**: A validation-scenarios CLI exists, but it is still aligned to the older V2-era API shape. It uses a local thin HTTP client, integer `MIMIR_TENANT_ID`, and deprecated `GET /search/fulltext` behavior. It is not yet an authoritative v5.5 contract/conformance suite.

**Scope**:
- Convert the tool to use the published `mimir-client` package and tenant shortnames.
- Exercise current v5 API behavior: unified `POST /search`, graph scope, context retrieval, provenance, tenant lifecycle, embeddings, and change outbox visibility.
- Provide scripted end-to-end scenarios runnable against any Mimir instance.
- Keep LLM/document-analysis examples as optional demos, not the core contract.

**Principle**: Mechanism — verifiable contract tests. This should verify what Mimir guarantees, not prescribe application ingestion or retrieval policy.

**Design documents**: `tools/validation-scenarios/docs/requirements.md`, `tools/validation-scenarios/docs/api-assessment.md`

**Dependencies**: None.

---

### Priority 2 — Outbox Runtime Handoff and Replay Validation

**Problem**: The Mimir outbox and Kafka publisher are implemented in v5.5.0, but runtime confidence depends on larnet wiring and an end-to-end validation trace. The remaining risk is operational, not architectural.

**Scope**:
- larnet service wiring for `python -m mimir.outbox_publisher`.
- Kafka topic/retention documentation for `mimir.changes.v1`.
- Smoke validation: API write creates outbox row, publisher sends Kafka event, `published_at` updates only after acknowledgement.
- Failure validation: Kafka outage leaves rows unpublished; restart drains backlog; consumers can deduplicate by `event_id` and resume by `sequence`.
- Efforts projection rebuild trace, or an explicit deferral with rationale.

**Principle**: Durable replay belongs to Mimir's outbox; Kafka is live delivery. Do not let infrastructure docs imply exactly-once delivery or infinite Kafka retention.

**Design documents**: `docs/change-events.md`, `docs/change-outbox-architecture.md`, `docs/v5.5.0-release-notes.md`

**Dependencies**: Mimir v5.5.0+ deployed with migrations; Kafka available in the target runtime.

---

### Priority 3 — Graph Engine Extensions

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

**Dependencies**: `mimir-client`, `mimir-embeddings`, and a concrete application retrieval/ingestion policy.

---

## What About Retrieval Strategies, Context Assembly, Ingestion Pipelines?

These are **application-level policy**, not library-level mechanism:

- **Retrieval strategy** (naive, parent-child, graph-aware): The Mimir backend already provides unified search with strategy inference, graph scoping, and hybrid modes via `POST /search`. The `mimir-client` exposes all of these. No wrapper library is needed.
- **Context assembly** (token budgeting, artifact selection): The Mimir backend already provides graph-based context retrieval via `POST /context/{artifact_id}`. Token budgeting for a specific LLM is an application concern.
- **Ingestion workflows** (chunk, store, relate, embed): How to decompose content into artifacts is domain-specific. A chat application chunks by turns. A documentation system chunks by sections. A code analysis tool chunks by functions. There is no generic "right answer" — this is policy.

If multiple applications converge on shared patterns, extract those patterns into utilities at that point. Not before.

---

## Completed: Client Library v5.3.0 (CLI-01: Tenant Shortname Migration)

**Status**: Complete in `mimir-client` v5.3.0 and carried forward in v5.5.1.

**Problem addressed**: `mimir-client` v5.2.0 exposed `tenant_id: int` as the primary tenant identifier, but the Mimir domain identifies tenants by string shortname. This forced consumers to resolve shortnames to integers before constructing the client -- a leaked abstraction that created friction for new customers and downstream frameworks (e.g., ooda_framework MemoryProtocol).

**Scope**:
- Replace `tenant_id: int` with `tenant: str` (shortname) as primary constructor parameter
- Lazy resolution of shortname to integer via existing `GET /tenants/by-shortname/{shortname}` endpoint
- Deprecate `tenant_id: int` and `MIMIR_TENANT_ID` env var (removal in v6.0.0)
- Both sync (`MimirSyncClient`) and async (`MimirClient`) clients

**Principle**: Mechanism -- the client translates the domain identifier to the infrastructure identifier. No policy about how tenants are organized.

**Multi-tenant agents**: The recommended pattern for agents operating across multiple tenants (e.g., organization knowledge graph + practices knowledge graph + project knowledge graph) is one client instance per tenant. This is explicit, stateless per-client, and avoids mutable tenant state.

**Design documents**: `clients/python/docs/cli-01-design.md`, `clients/python/docs/cli-01-technical-design.md`

**Dependencies**: None.

---

## v6.0.0 Horizon — Multi-Tenant Agent Experience

Based on feedback from the RADEMO1 customer engagement, their agent systems will operate across multiple Mimir tenants simultaneously. The v5.3.0 one-client-per-tenant pattern handles this correctly. v6.0.0 will evaluate whether deeper multi-tenant support is warranted based on production usage patterns.

**Candidate items (not committed, pending customer feedback):**

| Item | Description | Trigger |
|------|-------------|---------|
| **Shared connection pool** | Multiple client instances sharing one httpx connection pool for the same backend | Many-tenant deployments (10+) where TCP overhead matters |
| **Cross-tenant context assembly** | Native support for graph traversal across tenant boundaries | Agent systems that need to synthesize knowledge from multiple knowledge graphs in a single context window |
| **Per-call tenant override** | Shortname-based tenant parameter on individual data methods | Scripts or agents that rapidly traverse many tenants with a single client instance |
| **`tenant_id` removal** | Remove deprecated `tenant_id: int` constructor parameter and `MIMIR_TENANT_ID` env var | v6.0.0 breaking change, completing the migration started in v5.3.0 |

These items will be evaluated after RADEMO1 deploys multi-tenant agents in production. The architecture from v5.3.0 does not prevent any of these additions.

---

## Long-Term Vision (from Requirements V2/V3)

These are not currently scheduled but represent the broader product direction:

- **V2 — Meta-workflow and Reflective Analysis**: Intent drift detection, redundancy detection, conversation meta-analysis
- **V3 — Multi-ontology and Synthesis Engine**: Ontology views, cross-intent synthesis, longitudinal insight

See `docs/requirements.md` for the full vision statement.
