# PostgreSQL Base Image Enhancement: Apache AGE

**Status**: Requirements  
**Date**: 2025-02-13  
**Related**: `docs/graph-search-design.md` (§7.1, §9, §11.1)  
**Base Image**: `postgres-batteries-inc` ([repo](file:///Users/ldawson/repos/docker_images/postgres-batteries-inc))

---

## 1. Business Need

Mímir requires graph query capabilities (multi-hop traversal, path finding, pattern matching) to support its core knowledge graph use case. The design document (`graph-search-design.md`) specifies Apache AGE as the graph engine, running as a PostgreSQL extension inside the existing database. The `postgres-batteries-inc` Docker image must be enhanced to include Apache AGE alongside its existing extensions.

---

## 2. Current Base Image

The `postgres-batteries-inc` image currently provides:

| Component | Version | Purpose |
|-----------|---------|---------|
| PostgreSQL | 18 | Core database |
| pgvector | Latest (compiled from source) | Vector similarity search |
| PostGIS | 3 (apt package) | Geospatial (+ topology, raster) |
| pgRouting | Via apt | Graph algorithms for spatial routing |
| TIGER Geocoder | Via PostGIS | US address geocoding |
| pg_trgm | Built-in | Trigram similarity |
| fuzzystrmatch | Built-in | Fuzzy string matching |
| btree_gist | Built-in | GiST indexing |
| unaccent | Built-in | Accent-insensitive search |
| hstore | Built-in | Key-value store type |

**Build characteristics**:
- Base: `postgres:18` official image
- Multi-arch: `linux/amd64,linux/arm64` via Docker BuildX (`cloud-dawsonlp-arm64` builder)
- pgvector compiled from source (git clone, make, make install)
- PostGIS installed via `apt-get` (pre-built package)
- Init script (`01-init-extensions.sql`) runs `CREATE EXTENSION` for all extensions at container startup
- Published to Docker Hub as `dawsonlp/postgres-batteries-inc`

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Rationale |
|----|-------------|-----------|
| **F1** | The image MUST include Apache AGE 1.7.0 (or latest stable) compiled and installed as a PostgreSQL extension | AGE 1.7.0 is the current stable release with PG 18 support |
| **F2** | AGE MUST be loadable via `CREATE EXTENSION age` in any database | Standard PostgreSQL extension loading pattern |
| **F3** | AGE MUST be functional on both `linux/amd64` and `linux/arm64` architectures | Existing multi-arch requirement inherited from base image |
| **F4** | All existing extensions (pgvector, PostGIS, pg_trgm, etc.) MUST continue to work unchanged | No regressions; AGE is additive |
| **F5** | The `age` extension MUST be added to the init script (`01-init-extensions.sql`) so it is created automatically on first container startup | Consistent with existing extension initialization pattern |
| **F6** | AGE MUST be usable alongside pgvector within the same database and the same transaction | Mímir uses both pgvector (embeddings) and AGE (graph) in the same PostgreSQL instance |

### 3.2 Build Requirements

| ID | Requirement | Rationale |
|----|-------------|-----------|
| **B1** | AGE MUST be compiled from source during the Docker image build | No pre-built apt package exists for AGE on PG 18; follows same pattern as pgvector |
| **B2** | The build MUST use the official Apache AGE release tarball or git tag (not an arbitrary commit) | Reproducible builds; known-good release |
| **B3** | The build MUST succeed on the existing `cloud-dawsonlp-arm64` BuildX builder | Existing build infrastructure; no new builders required |
| **B4** | AGE compilation dependencies MUST be installed and then cleaned up in the same Docker layer to minimize image size | Follows existing pattern (pgvector build deps are installed, used, then removed) |


### 3.3 Runtime Requirements

| ID | Requirement | Rationale |
|----|-------------|-----------|
| **R1** | `shared_preload_libraries` in `postgresql.conf` MUST include `'age'` | AGE requires preloading; this is a documented AGE requirement |
| **R2** | The `ag_catalog` schema MUST be accessible to the database user | AGE stores its internal functions/types in `ag_catalog`; queries need access |
| **R3** | AGE graph operations MUST work within standard PostgreSQL transactions (BEGIN/COMMIT/ROLLBACK) | Transactional consistency is a non-negotiable constraint per the design document |
| **R4** | The container MUST start and pass health checks within the existing timeout (30 seconds) | No degradation to container startup time |

### 3.4 Testing Requirements

| ID | Requirement | Rationale |
|----|-------------|-----------|
| **T1** | The smoke test MUST verify that `CREATE EXTENSION age` succeeds | Basic extension loading verification |
| **T2** | The smoke test MUST verify that a graph can be created (`SELECT create_graph('test_graph')`) | Graph creation is the first operation after extension loading |
| **T3** | The smoke test MUST verify that a Cypher query executes successfully (create vertex, query vertex) | End-to-end graph operation verification |
| **T4** | The smoke test MUST verify that AGE and pgvector both work in the same database | Co-existence is a critical requirement for Mímir |
| **T5** | Existing smoke tests MUST continue to pass | No regressions |

---

## 4. AGE Build Dependencies

Based on [Apache AGE build documentation](https://age.apache.org/age-manual/master/intro/setup.html), the following build dependencies are required:

| Dependency | Purpose | Already in base image? |
|------------|---------|----------------------|
| `postgresql-server-dev-18` | PG extension build headers | Yes (used for pgvector) |
| `build-essential` | gcc, make | Yes (used for pgvector) |
| `libreadline-dev` | Readline support | Verify |
| `zlib1g-dev` | Compression | Verify |
| `flex` | Lexer generation for Cypher parser | **No — must be added** |
| `bison` | Parser generation for Cypher parser | **No — must be added** |
| `git` | Source checkout (if using git clone) | Yes (used for pgvector) |

**Key difference from pgvector**: AGE requires `flex` and `bison` for its Cypher parser compilation. These are not needed by pgvector and are likely not in the current build layer. They must be added to the build dependencies and cleaned up after compilation.

---

## 5. Configuration Changes

### 5.1 postgresql.conf

AGE requires being added to `shared_preload_libraries`. The current image may not set this parameter. Options:

| Approach | Mechanism |
|----------|-----------|
| **Docker entrypoint flag** | Add `-c shared_preload_libraries=age` to the container command |
| **Custom postgresql.conf** | Include a conf.d snippet that sets the parameter |
| **Init script** | Use `ALTER SYSTEM SET shared_preload_libraries = 'age'` (requires restart, not ideal for init) |

The technical design should determine which approach integrates best with the existing image's configuration strategy. The entrypoint flag approach is simplest and most explicit.

### 5.2 Search Path

AGE functions reside in the `ag_catalog` schema. For convenient use, the database search path should include `ag_catalog`:

```sql
SET search_path = ag_catalog, "$user", public;
```

This can be set per-session in the application or as a database-level default. The init script should set it as a database default.

---

## 6. Init Script Changes

The existing `01-init-extensions.sql` creates extensions on startup. It must be extended:

```sql
-- Add after existing CREATE EXTENSION statements:
CREATE EXTENSION IF NOT EXISTS age;

-- Set search path to include ag_catalog
ALTER DATABASE current_database() SET search_path = ag_catalog, "$user", public;
```

**Note**: The `LOAD 'age'` command may also be required in each session. The technical design should determine whether this is handled at the init script level, application level, or via `shared_preload_libraries` (which makes it automatic).

---

## 7. Acceptance Criteria

The enhanced image is accepted when:

1. `docker compose up` starts the container successfully with AGE loaded
2. All existing extensions continue to function (PostGIS, pgvector, pg_trgm, etc.)
3. The following sequence executes without error:
   ```sql
   CREATE EXTENSION age;
   SELECT create_graph('test');
   SELECT * FROM cypher('test', $$ CREATE (n:Person {name: 'Test'}) RETURN n $$) AS (result agtype);
   SELECT * FROM cypher('test', $$ MATCH (n:Person) RETURN n $$) AS (result agtype);
   SELECT drop_graph('test', true);
   ```
4. The image builds successfully for both `linux/amd64` and `linux/arm64`
5. Existing smoke tests pass
6. New AGE smoke tests pass
7. Image size increase is reasonable (< 50MB over current image)

---

## 8. Out of Scope

The following are NOT part of this image enhancement:

- Mímir-specific graph schemas or migrations (handled by Mímir's migration system)
- AGE Python driver installation (handled by application containers)
- Graph query performance tuning (handled at application level)
- Tenant graph creation (handled by Mímir's application code)
- AGE Viewer or other GUI tools