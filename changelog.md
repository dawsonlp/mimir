# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

[3.0.0]: https://github.com/dawsonlp/mimir/compare/v2.0.0...v3.0.0
[2.0.0]: https://github.com/dawsonlp/mimir/releases/tag/v2.0.0