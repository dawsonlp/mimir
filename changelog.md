# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [5.0.4] - 2026-02-21

### Added
- `mimir-client`: `search_semantic()` convenience method — vector search with pre-computed embeddings
- `mimir-client`: `search_hybrid()` convenience method — combined fulltext + vector search
- `mimir-client`: `search_similar()` convenience method — find similar artifacts by existing embedding
- All new methods delegate to the unified `search()` with typed parameters and clear docstrings

## [5.0.3] - 2026-02-21

### Fixed
- Ruff lint/format across all test files (imports, formatting, trailing newlines)
- `TemporalHint` import in `context_service.py` (was referencing removed class)

### Changed
- Ruff config: suppress UP042 (str+Enum → StrEnum may affect Pydantic serialization)
- Ruff config: suppress B017 (pytest.raises(Exception) acceptable in validation tests)

## [5.0.2] - 2026-02-21

### Added
- `mimir-client` async HTTP client implementation (PyPI: `pip install mimir-client`)
  - Full typed Pydantic response models for all API resources
  - `MimirClient` with async context manager, automatic tenant header injection
  - Convenience methods: `ensure_tenant()`, `ensure_artifact_type()`, `ensure_relation_type()`, `ensure_embedding_type()`
  - `search()` unified search + `search_fulltext()` convenience method
  - Structured error handling: `MimirNotFoundError`, `MimirConflictError`, `MimirValidationError`, `MimirServerError`
  - `MimirClientSettings` with environment variable support (`MIMIR_API_URL`, `MIMIR_TENANT_ID`)

## [5.0.1] - 2026-02-21

### Fixed
- AGE Cypher triggers: replaced `quote_literal()` with `cypher_literal()` in all PL/pgSQL trigger functions that build Cypher queries inside `$cypher$` blocks. `quote_literal()` emits PostgreSQL `E'…'` syntax which the Cypher parser rejects, causing 500 errors on artifact titles containing apostrophes (e.g., "What's Next").
  - `trg_artifact_create_vertex()`
  - `trg_artifact_delete_vertex()`
  - `trg_relation_create_edge()`
  - `trg_relation_delete_edge()`
  - `rebuild_tenant_graph()`
- Docker Compose image tags updated from v4.0.5 to v5.0.1

### Added
- `cypher_literal()` PL/pgSQL helper function: escapes backslashes and single quotes, wraps in plain single quotes for valid Cypher string literals
- Integration tests for artifact titles containing apostrophes, backslashes, and mixed special characters
- `mimir-client` Python package published to PyPI (`pip install mimir-client`)

### Changed
- CI release pipeline: `publish-client` job uses `uv build` + `uv publish` instead of `pip install build` + `pypa/gh-action-pypi-publish`

## [5.0.0] - 2026-02-20

### Breaking Changes
- Removed `DELETE /artifacts/{id}` endpoint (artifact-level deletion no longer supported)
- Removed `include_deleted` query parameters from all read endpoints
- Removed `deleted_at` field from `ArtifactResponse` schema
- Removed `deletion_policy` field from `TenantResponse` schema

### Removed
- Artifact-level soft-delete and physical-delete infrastructure (~850 lines removed)
  - `DELETE /artifacts/{id}` endpoint
  - `include_deleted` query parameters on all read paths
  - `deleted_at` field from artifact responses and database queries
  - `deletion_policy` from tenant type and tenant responses
  - `SoftDeleteResponse` and `PhysicalDeleteResponse` schemas
  - Migration 006 (deletion infrastructure: `deleted_at` column, `deletion_policy` column, partial index)
  - AGE graph soft-delete trigger (`trg_artifact_soft_delete_vertex`)
  - Double-JOIN artifact filters in relation, embedding, and search queries
  - `test_deletion_phase2.py` integration tests
  - `docs/soft-delete-semantics.md` specification

### Fixed
- Graph engine: AGE requires graph name as SQL string literal, not parameterized query value
- Graph engine: Cypher variable `end` renamed to `dest` (reserved keyword in AGE/Cypher)
- Agtype parser: Handle `::path` suffix in addition to `::vertex` and `::edge`
- test_api: `test_artifact_crud_lifecycle` updated for append-only model (removed PATCH/DELETE assertions)
- test_api: Fixed provenance URL path (`/provenance/artifact/{id}` not `/provenance/entity/artifact/{id}`)
- test_graph_scoped_search: Use unique shortnames per test run to avoid duplicate key errors on re-run

### Added
- `DELETE /tenants/{tenant_id}` endpoint for complete tenant removal via FK CASCADE
  - Drops tenant's AGE graph
  - Cascades through all content tables: artifacts, relations, embeddings, provenance events
  - Returns 204 on success, 404 if tenant not found
- `delete_tenant()` function in tenant service

### Changed
- Relation queries simplified: removed double-JOIN to artifact table for deleted_at checks
- Embedding queries simplified: removed JOIN to artifact table for deleted_at checks
- Search queries simplified: removed 5 `deleted_at IS NULL` clauses
- Context service simplified: removed soft-delete exclusion from `_strip_content()`
- AGE graph projection migration renumbered from 007 to 006
- `rebuild_tenant_graph()` SQL function: removed `deleted_at IS NULL` filters from vertex/edge rebuild queries

## [4.0.0] - 2026-02-15

### Added

- **Graph Traversal Engine** — Cypher-based graph traversal via Apache AGE, replacing Python-side BFS
  - `traverse()` — variable-length path queries with configurable depth, direction, and relation type filtering
  - `find_paths()` — find shortest paths between two artifacts using VLP + ORDER BY length
  - Full relation path data returned for argument chain validation (D3 requirement)
  - Per-query timeout enforcement via `SET LOCAL statement_timeout` (D6)
- **agtype parser** — pure-function parser for AGE's `agtype` return values (`::vertex`/`::edge` suffix stripping + JSON parsing)
- **Graph-scoped search** — new `graph_scope` parameter on `POST /search` for traverse-then-search pattern
  - `GraphScope` model with `root_artifact_id`, `max_depth`, `relation_types`, `direction`
  - Mutually exclusive with `scope_artifact_id` (422 if both provided)
  - `scope_artifact_id` backward compatibility preserved (internally converts to depth-1 graph_scope)
- **Graph engine configuration** — three new env vars: `MIMIR_GRAPH_MAX_DEPTH` (default 10), `MIMIR_GRAPH_MAX_RESULT_SET` (default 500), `MIMIR_GRAPH_QUERY_TIMEOUT_SECONDS` (default 5)
- **Graph engine exceptions** — `GraphScopeTooLargeError` (→ HTTP 422), `GraphQueryTimeoutError` (→ HTTP 504), `GraphNotFoundError` (→ HTTP 404)
- Graph engine schemas: `TraversalResult`, `PathStep`, `PathResult` dataclasses
- 48 new unit tests for agtype parser, Cypher builders, path extraction, and relation type filtering
- Integration tests for graph traversal (14 test cases) and graph-scoped search (8 test cases)

### Changed

- **Context service migrated to graph engine** — `_traverse_graph()` now delegates to `graph_engine.traverse()` instead of performing iterative BFS with per-hop SQL queries (N+1 → single Cypher query)
- Policy configurations updated from `directions: list[str]` to `direction: str` format for graph engine compatibility
- API version bumped to 4.0.0

### Performance

- Context retrieval traversal reduced from N+1 SQL queries (one per hop per artifact) to a single Cypher VLP query executed inside PostgreSQL/AGE
- Python-side relation type filtering applied post-query (AGE 1.7.0 lacks `ALL()` predicate)

## [3.0.0] - 2026-02-13

### Breaking Changes

- **Unified search endpoint** (`POST /v1/tenants/{tenant_id}/search`) replaces all legacy search endpoints
- Removed `POST /v1/tenants/{tenant_id}/search/semantic`
- Removed `POST /v1/tenants/{tenant_id}/search/hybrid`
- Removed `GET /v1/tenants/{tenant_id}/search/similar/{artifact_id}`
- `GET /v1/tenants/{tenant_id}/search/fulltext` retained with RFC 8594 deprecation headers (sunset: 2026-08-01)

### Added

- **Unified search endpoint** with four strategies inferred from request parameters:
  - `fulltext` — trigram-based text search with `ts_rank` scoring
  - `semantic` — pgvector cosine similarity against embedding vectors
  - `hybrid` — RRF fusion of fulltext + semantic results
  - `similar` — find artifacts similar to a given artifact by its embedding
- **Strategy inference** — server selects strategy automatically from request fields; explicit `strategy` override available
- **Metadata filtering** on all search strategies via `metadata_filter` (key-value JSONB containment)
- **Hierarchy scoping** via `scope_artifact_id` — recursive CTE walks parent→child relations to restrict results to a subtree
- **Pagination** on all strategies with `limit` and `offset` (defaults: 20/0)
- **Similar search** via `similar_to_id` field — finds nearest neighbors by embedding vector
- **Soft-delete infrastructure** — `deleted_at` column on artifacts, cascade marking of relations/embeddings, excluded from all queries by default
- **Cascade deletion** — soft-deleting an artifact marks its relations and embeddings as deleted
- Migration 006: deletion infrastructure (adds `deleted_at` columns and indexes)
- Comprehensive search architecture documentation (`docs/search-architecture.md`)
- Unified search technical design document (`docs/unified-search-technical-design.md`)
- Soft-delete behavioral specification (`docs/soft-delete-semantics.md`)
- Consumer migration guide (`comms/06_v3_migration_guide.md`)

### Changed

- Search response schema now returns `strategy` field indicating which strategy was used
- `SearchResponse.results` uses consistent `SearchResult` model across all strategies
- API title changed to "Mímir V3"
- Health endpoint returns `version: "3.0.0"`
- Documentation de-duplicated across architecture, design, and evaluation docs

### Testing

- 93 unit tests covering schema validation, strategy inference, and edge cases
- 36 integration tests covering all search strategies end-to-end against live database
- Hierarchy performance tests for recursive CTE scoping
- Deletion phase 2 integration tests for cascade soft-delete behavior

## [2.0.0] - 2025-12-01

### Added

- Initial public API with separate search endpoints
- Artifact CRUD with metadata support
- Relation management (typed, directional)
- Embedding storage and retrieval with pgvector
- Provenance tracking
- Multi-tenant isolation
- Fulltext search with trigram indexes
- Semantic search with cosine similarity
- Hybrid search with RRF fusion
- Context assembly endpoint

[5.0.4]: https://github.com/dawsonlp/mimir/compare/v5.0.3...v5.0.4
[5.0.3]: https://github.com/dawsonlp/mimir/compare/v5.0.2...v5.0.3
[5.0.2]: https://github.com/dawsonlp/mimir/compare/v5.0.1...v5.0.2
[5.0.1]: https://github.com/dawsonlp/mimir/compare/v5.0.0...v5.0.1
[5.0.0]: https://github.com/dawsonlp/mimir/compare/v4.0.0...v5.0.0
[4.0.0]: https://github.com/dawsonlp/mimir/compare/v3.0.0...v4.0.0
[3.0.0]: https://github.com/dawsonlp/mimir/compare/v2.0.0...v3.0.0
[2.0.0]: https://github.com/dawsonlp/mimir/releases/tag/v2.0.0
