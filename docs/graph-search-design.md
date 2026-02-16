# Graph Search Design Document

**Status**: Draft (Revised)  
**Author**: Senior Architect  
**Date**: 2025-02-13  
**Revised**: 2025-02-13 — Incorporates Apache AGE as graph engine following architectural review  
**Scope**: Graph search capabilities for Mímir beyond v3.0.0  

---

## 1. Motivation: Why Mímir Needs a Graph Engine

### 1.1 Mímir's Core Purpose

Mímir exists to retain and query the graph of knowledge and decision-making. It was designed to support investigation and learning by preserving how knowledge connects, how arguments are structured, and how decisions are reached. The foundational use case is:

> A user constructs an argument. That argument has counter-arguments, each with a decision point recording whether the original argument survives the challenge. Each counter-argument is supported by research — statements connected to their sources with provenance tracking. The system enables instant recognition of bad arguments and the resulting efficiency in reasoning.

This produces structures like:

```
Claim: "Microservices improve deployment velocity"
  │
  ├── CounterArgument: "Distributed systems complexity offsets gains"
  │     ├── [decision: survives — complexity is manageable with proper tooling]
  │     ├── Research: "Google SRE report on microservice overhead"
  │     │     └── Source: Google SRE Book, Chapter 7 [provenance]
  │     └── Research: "Netflix deployment frequency study"
  │           └── Source: Netflix Tech Blog, 2024-03 [provenance]
  │
  ├── CounterArgument: "Team cognitive load increases"
  │     ├── [decision: partially survived — depends on team size]
  │     └── Research: "Team Topologies cognitive load framework"
  │           └── Source: Skelton & Pais, 2019 [provenance]
  │
  └── SupportingEvidence: "Spotify squad model deployment metrics"
        └── Source: Spotify Engineering Blog [provenance]
```

The natural questions against this structure are graph-native:

- **Argument tree assembly**: "Show me the complete argument tree for this claim — all counter-arguments, their decisions, and the evidence chains."
- **Provenance tracing**: "What is the full source chain for this statement? Can I trust it?"
- **Impact analysis**: "Find all claims in this knowledge base that rest on a source that was later discredited." (Transitive — if a source is bad, everything built on it is suspect.)
- **Structural discovery**: "Which claims share supporting research?" (Common evidence across separate arguments.)
- **Scoped search**: "Search for 'cognitive load' but only within the argument tree rooted at this claim."

### 1.2 Why the Current Implementation Falls Short

Mímir v3.0.0 provides:
- **Single-hop relation filtering**: Find artifacts directly related to one artifact.
- **Hierarchy scoping**: Walk `parent_of` relations downward via recursive CTE.
- **Context assembly**: Python-side BFS traversal with configurable depth.

None of these can answer the questions above. Specifically:

| Question | Current Capability | Gap |
|----------|-------------------|-----|
| Argument tree assembly | Context service does multi-level BFS | Not integrated with search; fixed traversal logic; no relation-type filtering |
| Provenance tracing | Single-hop `related_to` filter | Cannot chain hops: claim → counter-argument → research → source |
| Impact analysis | Not possible | Requires reverse traversal from a discredited source through all dependent chains |
| Structural discovery | Not possible | Requires pattern matching: two claims sharing a common research node |
| Scoped search | `scope_artifact_id` with hardcoded `parent_of` | Cannot scope by arbitrary relation types or directions |

### 1.3 The Architectural Insight

The initial design (v1 of this document) treated graph search as a supplemental feature — an add-on to a text/semantic search system. The proposed approach was to implement all graph operations using hand-crafted PostgreSQL recursive CTEs.

Architectural review revealed this was backwards. **Graph traversal is Mímir's primary value delivery mechanism.** The text and semantic search capabilities supplement a knowledge graph, not the other way around. Building a graph engine out of recursive CTEs means:

- A multi-relation-type bidirectional traversal with cycle detection is 40-60 lines of SQL per operation
- Path finding requires even more complex CTEs
- Pattern matching in CTEs is genuinely unwieldy — each pattern shape requires different SQL
- Every new graph operation means writing and maintaining another complex CTE
- Developers must think in SQL recursion rather than stating graph questions naturally

This is fighting the abstraction. When the core value of the system is a knowledge graph, the graph query mechanism should match the domain — not force the domain into a relational paradigm.

### 1.4 Why Apache AGE

[Apache AGE](https://age.apache.org/) is a PostgreSQL extension that adds openCypher graph query support directly inside PostgreSQL. It stores graph data in PostgreSQL-managed tables and lets you query it with Cypher — the industry-standard graph query language.

**AGE 1.7.0** is the current stable release and supports **PostgreSQL 18** — Mímir's target database version.

The key advantages for Mímir:

1. **No separate database**: AGE runs inside PostgreSQL, alongside pgvector. One database. One backup strategy. One connection pool. One transaction boundary. The operational model Mímir already uses is preserved.

2. **No consistency problem**: When you create a relation in a transaction, the graph is updated in the same transaction. No dual-write. No sync lag. No eventual consistency. This eliminates the most serious objection to using a graph database.

3. **Natural query language**: The questions users need to ask map directly to Cypher:

   ```cypher
   -- "Show me the argument tree for this claim"
   MATCH path = (claim)-[*1..10]->(leaf)
   WHERE claim.id = $artifact_id
   RETURN path

   -- "Find all claims resting on a discredited source"
   MATCH (claim)-[:counter_argument]->(ca)-[:supported_by]->(research)-[:sourced_from]->(source)
   WHERE source.discredited = true
   RETURN claim, ca, research, source

   -- "Which claims share supporting research?"
   MATCH (claim1)-[:supported_by]->(research)<-[:supported_by]-(claim2)
   WHERE claim1 <> claim2
   RETURN claim1, research, claim2
   ```

   Compare these to the recursive CTEs that would be required for the same queries. The Cypher versions are readable, maintainable, and directly express the domain question.

4. **Proven extension model**: Mímir already uses pgvector as a PostgreSQL extension. AGE follows the same pattern — install the extension, create graphs, query with Cypher. The Docker PostgreSQL image adds one more extension.

5. **Future capability headroom**: AGE supports variable-length paths, shortest path algorithms, graph aggregation, and pattern matching natively. These capabilities are available without additional implementation effort when the need arises.

---

## 2. Current State Assessment

### 2.1 What Exists

| Capability | Mechanism | Limitation |
|------------|-----------|------------|
| **Single-hop relation filter** | `related_to` + `relation_type` + `relation_direction` on unified search | One hop only; cannot chain |
| **Hierarchy scoping** | Recursive CTE on `parent_of` relations via `scope_artifact_id` | Single relation type (`parent_of`); not configurable |
| **Context assembly** | `context_service` traverses relations with configurable depth and relation types | Read-only assembly; not integrated with search filtering; Python-side BFS |
| **Relation storage** | `relation` table: `source_artifact_id → target_artifact_id` with `relation_type` | No graph indexes; no path metadata; no materialized closures |

### 2.2 Relation Table Schema (Current)

```sql
relation (
  id              UUID PK,
  tenant_id       UUID FK → tenant,
  source_artifact_id UUID FK → artifact,
  target_artifact_id UUID FK → artifact,
  relation_type   TEXT NOT NULL,
  metadata        JSONB,
  created_at      TIMESTAMPTZ,
  updated_at      TIMESTAMPTZ,
  UNIQUE(tenant_id, source_artifact_id, target_artifact_id, relation_type)
)
```

Indexes exist on `(tenant_id, source_artifact_id)` and `(tenant_id, target_artifact_id)`. No composite graph-traversal indexes exist.

### 2.3 Recursive CTE Pattern (Current)

The hierarchy scoping in `search_service` uses a recursive CTE that walks `parent_of` relations from a root artifact downward. This pattern is sound but hardcoded to one relation type and one direction. The context service uses a similar iterative approach (Python-side BFS with depth limiting).

---

## 3. Requested Graph Search Capabilities

From the enhancement requests, four distinct graph search capabilities are identified, ordered by user value and architectural impact:

### 3.1 Multi-Hop Traversal Search

**Need**: Find artifacts reachable from a starting artifact through N hops of specified relation types.

**Example**: "Find all artifacts within 3 hops of `artifact-123` via `depends_on` or `implements` relations."

**Knowledge graph example**: "Show me everything connected to this claim — counter-arguments, their supporting research, and the sources."

**Distinction from hierarchy scoping**: Hierarchy scoping is a special case of multi-hop traversal (single relation type, single direction, unlimited depth). Multi-hop traversal generalizes this.

### 3.2 Graph-Scoped Search

**Need**: Combine text/semantic search with graph traversal — search only within a subgraph defined by traversal from a root node.

**Example**: "Search for 'authentication' within everything reachable from my architecture document."

**Knowledge graph example**: "Search for 'cognitive load' but only within the argument tree for this specific claim."

**Distinction from current `scope_artifact_id`**: Current scoping only walks `parent_of`. Graph-scoped search walks any combination of relation types and directions.

### 3.3 Path Finding

**Need**: Discover the relation path(s) between two artifacts.

**Example**: "How is `artifact-A` connected to `artifact-B`?" → Returns `A --implements--> C --depends_on--> B`.

**Knowledge graph example**: "How does this source connect to this claim?" → Returns the full provenance chain: `Source --sourced_from-- Research --supported_by-- CounterArgument --counter_argument-- Claim`.

### 3.4 Relation Pattern Matching

**Need**: Find artifacts matching structural patterns in the graph.

**Example**: "Find artifacts that `implements` something of type `interface` AND `depends_on` something of type `library`."

**Knowledge graph example**: "Find all claims that share a common piece of supporting research" (two claims pointing to the same research artifact through any path).

---

## 4. Component Architecture

### 4.1 Component Boundaries

```
┌──────────────────────────────────────────────────────────────┐
│                      Unified Search Endpoint                  │
│                  POST /v1/tenants/{tid}/search                │
└──────────────┬───────────────────────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────────────────────┐
│                      Search Orchestrator                      │
│  Determines strategy, delegates to search + graph components  │
└──────┬──────────────────┬────────────────────────┬───────────┘
       │                  │                        │
       ▼                  ▼                        ▼
┌──────────────┐  ┌───────────────┐  ┌──────────────────────┐
│ Text/Semantic │  │   Graph       │  │   Result Compositor   │
│ Search        │  │   Traversal   │  │                      │
│ (existing)    │  │   Engine      │  │  Merges search hits  │
│               │  │   (AGE/Cypher)│  │  with graph scope    │
└──────────────┘  └───────┬───────┘  └──────────────────────┘
                          │
                          ▼
                  ┌───────────────┐
                  │  Apache AGE   │
                  │  Graph Store  │
                  │  (PostgreSQL) │
                  └───────────────┘
```

**Four components. Three are new.**

| Component | Responsibility | Does NOT Do |
|-----------|---------------|-------------|
| **Search Orchestrator** (exists, extended) | Receives unified search request; coordinates search strategy with graph constraints; returns merged results | Graph traversal logic; text/semantic search logic |
| **Text/Semantic Search** (exists) | Full-text search, vector similarity, hybrid scoring | Graph awareness; relation traversal |
| **Graph Traversal Engine** (new) | Multi-hop traversal, path finding, subgraph extraction, pattern matching — via Cypher queries against AGE | Text search; semantic similarity; result ranking |
| **Result Compositor** (new) | Intersects graph-scoped artifact sets with search result sets; applies pagination and ordering to composed results | Traversal; search; scoring |

### 4.2 Why a Separate Graph Traversal Engine

The graph traversal engine must be a distinct component from the search service because:

1. **Different computational model**: Search is set-based (find matching rows). Graph traversal is path-based (walk edges, match patterns). Mixing them produces neither-fish-nor-fowl code.
2. **Independent testability**: Graph traversal correctness (cycle detection, depth limiting, direction handling) must be testable with no search dependencies.
3. **Performance isolation**: A runaway traversal (large fan-out) must be bounded independently from search query timeouts.
4. **Reuse**: The context service already does graph traversal. The graph traversal engine should replace and generalize that logic, serving both context assembly and graph-scoped search.

### 4.3 Context Service Convergence

The existing context service performs ad-hoc graph traversal (Python-side BFS). This duplicates what the graph traversal engine will provide. Once the graph traversal engine exists:

- The context service becomes a **consumer** of the graph traversal engine
- Context assembly = graph traversal (get subgraph) + artifact hydration (get full content)
- The context service retains its own interface but delegates traversal

This is not a breaking change. The context service contract does not change; only its internal dependency graph shifts.

---

## 5. Interfaces Between Components

### 5.1 Graph Traversal Engine Interface

The graph traversal engine exposes these operations to internal consumers (search orchestrator, context service):

**Operation: Traverse**

| Input | Type | Description |
|-------|------|-------------|
| `tenant_id` | UUID | Tenant scope |
| `start_artifact_ids` | Set\<UUID\> | One or more starting nodes |
| `relation_types` | Set\<String\> | Which relation types to follow (empty = all) |
| `directions` | Set\<Direction\> | `outbound`, `inbound`, or `both` |
| `max_depth` | Integer | Maximum hops (required; no unbounded traversal) |
| `include_start` | Boolean | Whether starting nodes appear in result set |
| `exclude_deleted` | Boolean | Respect soft-delete |

| Output | Type | Description |
|--------|------|-------------|
| `artifact_ids` | Set\<UUID\> | All artifacts reachable within constraints |
| `depth_map` | Map\<UUID, Integer\> | Shortest distance from any start node to each reachable artifact |

**Operation: Find Paths**

| Input | Type | Description |
|-------|------|-------------|
| `tenant_id` | UUID | Tenant scope |
| `from_artifact_id` | UUID | Starting node |
| `to_artifact_id` | UUID | Target node |
| `relation_types` | Set\<String\> | Which relation types to follow (empty = all) |
| `directions` | Set\<Direction\> | `outbound`, `inbound`, or `both` |
| `max_depth` | Integer | Maximum path length (required) |

| Output | Type | Description |
|--------|------|-------------|
| `paths` | List\<Path\> | Ordered list of paths, shortest first |

Where `Path` is an ordered sequence of `(artifact_id, relation_type, direction)` steps.

**Operation: Match Pattern**

| Input | Type | Description |
|-------|------|-------------|
| `tenant_id` | UUID | Tenant scope |
| `pattern` | PatternSpec | Structural pattern to match (see §5.3) |
| `max_depth` | Integer | Per-edge hop limit |

| Output | Type | Description |
|--------|------|-------------|
| `matches` | List\<Map\<String, UUID\>\> | Variable bindings for each match |

### 5.2 Search Orchestrator Extended Interface

The unified search request gains these optional fields:

| Field | Type | Description |
|-------|------|-------------|
| `graph_scope` | GraphScope (optional) | Replace current `scope_artifact_id` with generalized graph scoping |
| `path_query` | PathQuery (optional) | Find paths between two artifacts |
| `pattern` | PatternSpec (optional) | Structural pattern matching |

**GraphScope** contains:

| Field | Type | Description |
|-------|------|-------------|
| `root_ids` | List\<UUID\> | Starting artifact(s) for traversal |
| `relation_types` | List\<String\> (optional) | Relation types to follow; empty = all |
| `directions` | List\<Direction\> (optional) | Default: `both` |
| `max_depth` | Integer | Required; enforced maximum |

**Backward Compatibility**: The existing `scope_artifact_id` field remains as syntactic sugar. When present, it is translated internally to a `GraphScope` with `root_ids=[scope_artifact_id]`, `relation_types=["parent_of"]`, `directions=["outbound"]`, `max_depth=unlimited` (system-configured ceiling).

### 5.3 Pattern Specification

Pattern matching uses a declarative graph pattern language. The pattern is a set of **nodes** (with optional metadata constraints) and **edges** (with relation type and direction constraints). Each node has a variable name. The engine returns all subgraphs matching the pattern.

```
PatternSpec:
  nodes:
    - name: "a"
      artifact_type: "interface"      # optional filter
      metadata_filter: {...}          # optional, same syntax as search metadata filters
    - name: "b"
      artifact_type: "component"
  edges:
    - from: "a"
      to: "b"
      relation_type: "implements"
      direction: "outbound"
```

This is intentionally a simple pattern language. It supports conjunctive node/edge patterns only. Disjunction, negation, and optional patterns are out of scope for the initial design.

The pattern specification maps naturally to Cypher `MATCH` clauses — the technical design phase will determine whether the API accepts the structured PatternSpec above (compiled to Cypher internally) or exposes a safe subset of Cypher directly.

---

## 6. Data Flows

### 6.1 Graph-Scoped Search Flow

```
Client → Unified Search Endpoint
  │
  ├─ 1. Search Orchestrator receives request with `graph_scope` + search query
  │
  ├─ 2. Search Orchestrator calls Graph Traversal Engine: Traverse(graph_scope)
  │     └─ Engine executes Cypher: MATCH (start)-[*1..N]->(reachable) WHERE start.id IN $roots
  │     └─ Returns: Set<artifact_id> (the scoped set)
  │
  ├─ 3. Search Orchestrator calls Text/Semantic Search with additional filter:
  │     artifact_id IN (scoped set)
  │     └─ Returns: ranked search results
  │
  ├─ 4. Result Compositor enriches results with depth_map metadata
  │
  └─ 5. Return to client
```

**Critical design decision**: The graph traversal executes **before** the text/semantic search. The traversal produces a set of artifact IDs that is passed as a filter to the search query. This is "traverse-then-search" ordering.

**Alternative considered**: "Search-then-filter" (run search first, then filter results by graph reachability). Rejected because:
- Search results are paginated; filtering after pagination produces inconsistent page sizes
- Graph reachability is a hard constraint, not a ranking signal — it should be applied before scoring

**Constraint**: If the traversal returns more artifact IDs than can be efficiently passed as an `IN` clause (system-configurable threshold, e.g., 10,000), the request must fail with a clear error rather than degrading silently. The client should narrow their graph scope.

### 6.2 Path Finding Flow

```
Client → Unified Search Endpoint (with path_query)
  │
  ├─ 1. Search Orchestrator extracts path_query
  │
  ├─ 2. Search Orchestrator calls Graph Traversal Engine: FindPaths(path_query)
  │     └─ Engine executes Cypher: MATCH path = shortestPath((a)-[*..N]-(b))
  │     └─ Returns: List<Path>
  │
  └─ 3. Return paths to client (no text/semantic search involved)
```

Path finding is a pure graph operation. It does not combine with text search. If a client sends both a search query and a path query in the same request, the request is rejected as invalid.

### 6.3 Pattern Matching Flow

```
Client → Unified Search Endpoint (with pattern)
  │
  ├─ 1. Search Orchestrator extracts pattern
  │
  ├─ 2. Search Orchestrator calls Graph Traversal Engine: MatchPattern(pattern)
  │     └─ Engine compiles PatternSpec to Cypher MATCH clause and executes
  │     └─ Returns: List<Map<variable_name, artifact_id>>
  │
  ├─ 3. If search query also present: use matched artifact IDs as scope filter
  │     (similar to graph-scoped search flow)
  │
  └─ 4. Return results
```

---

## 7. Constraints and Non-Negotiable Decisions

### 7.1 Apache AGE as the Graph Engine — Inside PostgreSQL

**Decision**: Graph operations will be implemented using Apache AGE 1.7.0, a PostgreSQL extension providing openCypher graph query support. No separate graph database will be introduced.

**Rationale**:

1. **Graph traversal is the primary value delivery mechanism.** Mímir's core purpose is knowledge graph construction and querying. The argument/counter-argument/provenance structures that define Mímir's use case are inherently graph structures. A graph query language (Cypher) expresses the domain questions naturally; recursive CTEs force the domain into a relational paradigm.

2. **No operational complexity increase.** AGE runs inside PostgreSQL as an extension, the same deployment model as pgvector. One database process. One backup. One connection pool. One transaction boundary. The Docker PostgreSQL image adds one more `CREATE EXTENSION` call.

3. **Transactional consistency preserved.** Because AGE operates within PostgreSQL, graph mutations occur in the same transaction as relational mutations. When a relation is created, the graph is immediately queryable. No dual-write problem. No sync lag. No eventual consistency. This is the decisive advantage over a separate graph database.

4. **Cypher over CTEs.** The queries Mímir needs — multi-hop traversal, path finding, pattern matching — are one-line Cypher statements vs. 40-60 line recursive CTEs. This is a maintenance and correctness difference, not just an ergonomic preference. Each new CTE is a surface for bugs; each Cypher query is a direct statement of intent.

5. **PG 18 compatibility confirmed.** AGE 1.7.0 is the current stable release with explicit PostgreSQL 18 support. No version compatibility risk.

**Fallback**: If AGE proves unsuitable in practice (performance, stability, driver maturity), recursive CTEs remain as a fallback. The Graph Traversal Engine interface (§5.1) is implementation-agnostic — consumers do not know or care whether Cypher or CTEs execute behind it.

### 7.2 Mandatory Depth Limits

**Decision**: Every graph traversal operation requires an explicit `max_depth` parameter. There is no "unlimited depth" option. The system enforces a configurable maximum ceiling (e.g., 20 hops).

**Rationale**: Unbounded graph traversal on arbitrary graph structures can produce catastrophic query plans regardless of the query engine. Depth limits are the primary safety mechanism. The existing `scope_artifact_id` hierarchy scoping (which currently has no explicit limit) will be retrofitted with a system-configured ceiling when migrated to the graph traversal engine.

### 7.3 Tenant Isolation

**Decision**: All graph traversal is strictly tenant-scoped. A traversal will never cross tenant boundaries, regardless of graph structure.

**Rationale**: This is an invariant inherited from the core Mímir architecture. The `tenant_id` predicate is applied at the graph query level, not as a post-filter. In AGE terms, each tenant's graph is a separate named graph, or tenant_id is a mandatory property on all vertices and edges with query-level filtering.

### 7.4 Soft-Delete Awareness

**Decision**: Graph traversal respects soft-delete by default. Deleted artifacts are excluded from traversal results and are not followed as intermediate hops. An explicit `include_deleted` flag may override this for administrative use cases.

**Rationale**: Consistent with v3.0.0 soft-delete semantics. A deleted artifact in the middle of a path effectively "breaks" that path for normal queries. This is the expected behavior — if a user deletes a bridge artifact, downstream artifacts become unreachable through that path.

### 7.5 Result Set Size Limits

**Decision**: Graph traversal operations return at most N artifact IDs (system-configurable, e.g., 10,000). If a traversal exceeds this limit, it fails with an error indicating the scope is too broad.

**Rationale**: Prevents memory exhaustion and excessively large `IN` clauses when composing graph scope with search. Forces clients to use tighter constraints rather than attempting whole-graph queries.

---

## 8. Trade-offs Considered

### 8.1 Traverse-Then-Search vs. Integrated Query

| Approach | Pros | Cons |
|----------|------|------|
| **Traverse-then-search** (chosen) | Simple composition; each component independently testable; graph scope is a clean artifact ID set | Two-phase execution; requires materialization of intermediate ID set; large scopes hit IN-clause limits |
| **Integrated query** (single SQL/Cypher) | Single query plan; optimizer can push predicates; no intermediate materialization | Complex query generation; tight coupling between search and graph logic; harder to test; harder to optimize independently |

**Decision**: Traverse-then-search. The simplicity and testability benefits outweigh the performance cost for Mímir's expected workload. The result set size limit (§7.5) bounds the materialization cost.

### 8.2 Apache AGE (Cypher) vs. Recursive CTEs vs. Separate Graph Database

| Approach | Pros | Cons |
|----------|------|------|
| **Apache AGE / Cypher** (chosen) | Graph-native query language; same PG instance; transactional consistency; natural fit for domain questions; pattern matching built-in | Additional PG extension; Python driver maturity to verify; AGE-specific schema management |
| **Recursive CTEs** (fallback) | No additional extensions; pure SQL; well-understood by DBA community | 40-60 lines per traversal; pattern matching unwieldy; each operation is a maintenance surface; fights the abstraction |
| **Separate graph DB** (rejected) | Best-in-class graph algorithms; mature tooling; purpose-built storage | Dual-write consistency problem; operational burden doubled; cross-database queries require coordination; unacceptable complexity for Mímir's scale |

**Decision**: Apache AGE. The core argument is that Mímir's primary value is knowledge graph querying. Expressing graph questions in a graph language is not a convenience — it is an architectural alignment between the problem domain and the solution domain. CTEs remain as a fallback if AGE proves unsuitable.

**Why not a separate graph database**: The consistency guarantee is non-negotiable. When a user creates a relation, that relation must be immediately queryable in graph operations within the same request lifecycle. A separate database introduces either synchronous dual-write latency or asynchronous staleness. For Mímir's scale (thousands to tens of thousands of relations per tenant, not millions), the operational cost of a second database is not justified by its performance characteristics.

### 8.3 Materialized Transitive Closure vs. On-Demand Traversal

| Approach | Pros | Cons |
|----------|------|------|
| **On-demand traversal** (chosen) | No storage overhead; always consistent; no write amplification on relation changes | Traversal cost paid on every query; deep/wide graphs are expensive |
| **Materialized closure table** | O(1) reachability checks; instant subgraph extraction | Write amplification on relation CRUD; storage grows quadratically; complex invalidation logic; eventual consistency risk |

**Decision**: On-demand traversal. AGE's index-free adjacency and Cypher's built-in path operations make on-demand traversal efficient for Mímir's expected graph sizes. Materialized closures are a premature optimization. If profiling reveals hot traversal paths, AGE's internal indexing can be tuned, or a closure cache can be added behind the graph traversal engine interface without changing consumers.

---

## 9. Graph Schema Design

### 9.1 The Mapping Question

The existing `relation` table stores graph edges in relational form. AGE stores graph data in its own internal tables using a vertex/edge model. The central schema question is: **does AGE become the primary store for graph structure, or does it mirror the relational `relation` table?**

### 9.2 Recommended Approach: AGE as Primary Graph Store

**Decision**: For graph search operations, AGE's graph becomes the authoritative representation of the artifact-relation graph. The relational `relation` table continues to exist for backward compatibility with existing non-graph queries (e.g., simple `related_to` filtering) but is kept in sync via the relation service.

**Vertex model** (maps to `artifact`):

| Property | Source | Description |
|----------|--------|-------------|
| `id` | `artifact.id` | UUID, primary identifier |
| `tenant_id` | `artifact.tenant_id` | Tenant scope |
| `artifact_type` | `artifact.artifact_type` | Type for pattern matching |
| `deleted_at` | `artifact.deleted_at` | Soft-delete timestamp (null = active) |
| `title` | `artifact.title` | For display in path results |

Vertices carry **only the properties needed for graph operations** (filtering, display in results). Full artifact content stays in the relational `artifact` table and is hydrated on demand.

**Edge model** (maps to `relation`):

| Property | Source | Description |
|----------|--------|-------------|
| Edge label | `relation.relation_type` | The relation type becomes the edge label in AGE |
| `id` | `relation.id` | UUID, for correlation with relational table |
| `tenant_id` | `relation.tenant_id` | Tenant scope |
| `metadata` | `relation.metadata` | JSONB, available for edge-property filtering |
| `created_at` | `relation.created_at` | Temporal queries |

### 9.3 Tenant Isolation in Graph Schema

Two approaches exist for tenant isolation in AGE:

| Approach | Pros | Cons |
|----------|------|------|
| **One AGE graph per tenant** | Complete isolation; no cross-tenant risk; simpler Cypher (no tenant_id filter) | Graph management overhead; dynamic graph creation on tenant provisioning |
| **Single graph with tenant_id property** | Simpler management; single graph to maintain | Every query must include tenant_id filter; cross-tenant leak risk if filter omitted |

This is a technical design decision, not an architectural one. Both approaches satisfy the tenant isolation constraint (§7.3). The technical design should evaluate which is more practical given AGE's graph management capabilities.

### 9.4 Sync Strategy

The relation service is the single point of mutation for relations. When it creates, updates, or deletes a relation in the relational `relation` table, it must also perform the corresponding AGE graph mutation in the same database transaction. This is straightforward because AGE operates within PostgreSQL — the same connection, the same transaction, the same commit.

The artifact service similarly must create/update/delete AGE vertices when artifacts are created, updated (type/title changes), soft-deleted, or hard-deleted.

**This is not a dual-write problem.** It is a single-database, single-transaction write to two representations within the same PostgreSQL instance. If the transaction commits, both representations are updated. If it rolls back, neither is.

---

## 10. Knowledge Graph Query Patterns

This section illustrates how Mímir's core knowledge graph questions map to Cypher queries through the Graph Traversal Engine. These are not implementation specifications — they demonstrate the expressiveness that motivates the AGE decision.

### 10.1 Argument Tree Assembly

**Question**: "Show me the complete argument tree for this claim."

```cypher
MATCH path = (claim)-[*1..10]->(descendant)
WHERE claim.id = $artifact_id
  AND claim.tenant_id = $tenant_id
  AND ALL(node IN nodes(path) WHERE node.deleted_at IS NULL)
RETURN path
```

Returns the full tree: claim → counter-arguments → decisions → research → sources. Each path is a branch of the argument tree.

### 10.2 Provenance Tracing

**Question**: "What is the full source chain for this statement?"

```cypher
MATCH path = (statement)-[:supported_by|sourced_from*1..5]->(source)
WHERE statement.id = $artifact_id
  AND statement.tenant_id = $tenant_id
  AND ALL(node IN nodes(path) WHERE node.deleted_at IS NULL)
RETURN path
```

Follows only provenance-relevant relation types. Returns every path from the statement to its ultimate sources.

### 10.3 Impact Analysis (Transitive)

**Question**: "Find all claims that rest on a discredited source."

```cypher
MATCH (claim)-[*1..10]->(source)
WHERE source.id = $discredited_source_id
  AND claim.tenant_id = $tenant_id
  AND claim.artifact_type = 'claim'
  AND ALL(node IN nodes(path) WHERE node.deleted_at IS NULL)
RETURN DISTINCT claim
```

This is a reverse traversal — starting from the bad source and finding everything that depends on it. In recursive CTEs, this requires constructing the CTE in reverse and joining back to filter by artifact type. In Cypher, the direction and filtering are declarative.

### 10.4 Structural Discovery

**Question**: "Which claims share supporting research?"

```cypher
MATCH (claim1)-[:supported_by*1..3]->(research)<-[:supported_by*1..3]-(claim2)
WHERE claim1 <> claim2
  AND claim1.tenant_id = $tenant_id
  AND claim1.artifact_type = 'claim'
  AND claim2.artifact_type = 'claim'
RETURN claim1, research, claim2
```

Pattern matching — two claims connected to the same research node through `supported_by` chains. This query shape is not expressible as a single recursive CTE without significant contortion.

### 10.5 Scoped Search (Combined with Text Search)

**Question**: "Search for 'cognitive load' within this argument tree."

This is a two-phase operation (§6.1):

1. Graph Traversal Engine executes:
   ```cypher
   MATCH (root)-[*1..10]->(descendant)
   WHERE root.id = $scope_root_id
     AND root.tenant_id = $tenant_id
     AND descendant.deleted_at IS NULL
   RETURN DISTINCT descendant.id AS artifact_id
   ```

2. Text/Semantic Search executes with `artifact_id IN (scoped set)` as an additional filter.

---

## 11. Migration Path from Current State

### 11.1 Phase 0: AGE Infrastructure (Foundation)

- Add Apache AGE 1.7.0 extension to the PostgreSQL Docker image (alongside pgvector)
- Create initial AGE graph schema
- Write migration to populate AGE graph from existing `artifact` and `relation` tables
- Update relation service to write to both relational table and AGE graph in same transaction
- Update artifact service to maintain AGE vertices on create/update/delete
- **No API changes.** Existing behavior unchanged.

### 11.2 Phase 1: Graph Traversal Engine + Multi-Hop Traversal

- Introduce the Graph Traversal Engine component with the `Traverse` operation (backed by AGE Cypher)
- Generalize the existing `scope_artifact_id` recursive CTE to use the engine internally
- Migrate `scope_artifact_id` to use `GraphScope` internally (backward compatible)
- Migrate context service to consume the graph traversal engine for its traversal logic

### 11.3 Phase 2: Graph-Scoped Search

- Add `graph_scope` field to the unified search request
- Implement traverse-then-search composition in the search orchestrator
- Add result compositor for depth metadata enrichment

### 11.4 Phase 3: Path Finding

- Add `FindPaths` operation to the graph traversal engine (backed by Cypher `shortestPath`)
- Add `path_query` field to the unified search request
- Implement path response format

### 11.5 Phase 4: Pattern Matching

- Add `MatchPattern` operation to the graph traversal engine
- Add `pattern` field to the unified search request
- Implement PatternSpec-to-Cypher compilation

Each phase is independently deployable and valuable. Phase 0 is purely infrastructure with no API impact. Phase 1 provides immediate value by consolidating existing graph logic and making it reusable.

---

## 12. Open Questions for Technical Design

These questions are intentionally left for the technical design phase:

1. **AGE Python driver**: Which Python library to use for AGE queries? Options include `age` (official Python driver), raw `psycopg` with AGE SQL syntax (`SELECT * FROM cypher('graph', $$ ... $$) AS (result agtype)`), or an async wrapper. The technical design should evaluate maturity, async support, and connection pooling compatibility.

2. **Tenant isolation strategy**: One AGE graph per tenant vs. single graph with tenant_id properties (see §9.3). Benchmark graph creation overhead, query performance with/without property filters, and operational management.

3. **Vertex lifecycle management**: When an artifact is created, should the AGE vertex be created immediately, or lazily on first graph query? Immediate is simpler and consistent; lazy reduces write overhead for artifacts that may never participate in graph operations.

4. **Soft-delete in graph**: Should soft-deleted vertices be removed from the AGE graph entirely (requiring re-insertion if undeleted) or marked with a `deleted_at` property (requiring filter in every query)? Trade-off between query simplicity and undelete support.

5. **Relation table retirement**: Long-term, should the relational `relation` table be retired in favor of AGE as the sole store for graph structure? This would simplify the sync requirement but requires all current relation-table consumers to be migrated to AGE queries.

6. **Index strategy in AGE**: AGE supports property indexes on vertices and edges. Which properties should be indexed? (Likely: `id`, `tenant_id`, `artifact_type`, `deleted_at` on vertices; `tenant_id` on edges.)

7. **API response format for paths**: How should paths be serialized? Flat list of hops? Nested structure? (API design decision, not architectural.)

8. **Docker image build**: AGE must be compiled from source for the PostgreSQL image (similar to pgvector). The Docker build process needs to include AGE compilation. Verify build compatibility with the existing multi-arch build pipeline.

---

## 13. Success Criteria

The graph search design is successful when:

1. **Multi-hop queries** execute in < 200ms for graphs with ≤ 100,000 relations and depth ≤ 10
2. **Graph-scoped search** latency is at most 1.5× the latency of equivalent unscoped search (for scopes ≤ 1,000 artifacts)
3. **Graph queries express domain questions naturally** — Cypher queries are readable by developers who understand the domain, without needing to understand recursive SQL
4. **No new infrastructure services** — AGE runs within PostgreSQL; no separate database process
5. **Transactional consistency** — graph is always consistent with relational data within the same transaction
6. **Backward compatibility** — existing `scope_artifact_id` and `related_to` behavior unchanged
7. **Context service** delegates to graph traversal engine with no change to its external interface
8. **Each phase** is independently deployable behind feature flags if needed

---

## Appendix A: Glossary

| Term | Definition |
|------|------------|
| **Apache AGE** | A PostgreSQL extension that adds openCypher graph query support. Stores graph data in PG-managed tables. |
| **Cypher** | A declarative graph query language, originally from Neo4j, standardized as openCypher. AGE implements openCypher. |
| **Hop** | A single relation traversal from one artifact to another |
| **Depth** | Number of hops from a starting artifact |
| **Subgraph** | The set of artifacts and relations reachable from a starting set within constraints |
| **Transitive closure** | The complete set of artifacts reachable through any number of hops (within depth limit) |
| **Fan-out** | The number of relations emanating from a single artifact |
| **Graph scope** | A subgraph used as a filter for text/semantic search |
| **Vertex** | AGE's representation of a node (maps to an artifact) |
| **Edge** | AGE's representation of a relationship (maps to a relation) |

## Appendix B: Relation to Existing Documents

| Document | Relationship |
|----------|-------------|
| `search-architecture.md` | Defines current search behavior; this document extends it with graph search |
| `unified-search-technical-design.md` | Technical design for v3.0.0 search; graph search technical design will extend it |
| `enhancement-request-evaluation.md` | Source of graph search requirements analyzed here |
| `enhancement-roadmap-checklist.md` | Tracks implementation progress; graph search phases should be added |
| `data-model.md` | Documents relation table schema referenced in §2.2 |

## Appendix C: Decision Log

| Date | Decision | Rationale |
|------|----------|-----------|
| 2025-02-13 (v1) | PostgreSQL recursive CTEs only; no graph database | Operational simplicity; single database |
| 2025-02-13 (v2) | **Revised**: Apache AGE as graph engine inside PostgreSQL | Graph traversal is primary value delivery; Cypher aligns query language with domain; AGE preserves single-database model; PG 18 supported (AGE 1.7.0) |
