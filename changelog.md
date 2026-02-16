# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

[4.0.0]: https://github.com/dawsonlp/mimir/compare/v3.0.0...v4.0.0
[3.0.0]: https://github.com/dawsonlp/mimir/compare/v2.0.0...v3.0.0
[2.0.0]: https://github.com/dawsonlp/mimir/releases/tag/v2.0.0
