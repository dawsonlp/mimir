# Mímir V2 API Enhancement Roadmap

## Overview

This document specifies prioritized API enhancements to support RAG (Retrieval Augmented Generation) workloads. Each enhancement is described in terms of requirements, behavior, and architectural considerations.

**Target Audience**: Senior engineers implementing these changes  
**Prerequisite**: Familiarity with Mímir V2 architecture documentation

---

## Priority Matrix

| Priority | Enhancement | Complexity | Impact |
|----------|-------------|------------|--------|
| **P0** | Batch Artifact Retrieval | Low | High |
| **P1** | Context Retrieval Service | High | Critical |
| **P2** | Relation-Aware Search Filters | Medium | Medium |
| **P3** | Graph Traversal Queries | High | Low |

---

## P0: Batch Artifact Retrieval ✅ COMPLETE

> **Implemented**: 2026-01-29  
> **Files Modified**: `backend/src/mimir/services/artifact_service.py`, `backend/src/mimir/routers/artifacts.py`

### Problem Statement
Currently, retrieving N artifacts requires N separate API calls. This creates unacceptable latency for clients that need to fetch multiple related artifacts.

### Requirements

**Endpoint**: `GET /artifacts`

**New Query Parameter**: `ids` (optional)
- Type: Comma-separated list of UUIDs
- Max items: 100
- Behavior: When present, ignores pagination parameters and returns only artifacts matching the provided IDs

**Response Changes**:
- Same `ArtifactListResponse` structure
- `total` reflects count of found artifacts
- Missing IDs should be silently omitted (not errors)

### Acceptance Criteria
1. Single request retrieves up to 100 artifacts by UUID
2. Order of returned artifacts matches order of requested IDs
3. Tenant isolation enforced (only returns artifacts belonging to X-Tenant-ID)
4. Performance: <50ms for 100 artifacts with warm cache

### Implementation Notes
- Use `WHERE id = ANY(%s)` for PostgreSQL efficiency
- Maintain existing list_artifacts function, add conditional branch for batch mode
- No new service function required—extend existing

---

## P1: Context Retrieval Service

### Problem Statement
RAG applications need to retrieve an artifact along with all contextually relevant artifacts in a single operation. This is not simply "artifact + relations"—it requires **policy-driven decisions** about what constitutes relevant context.

### Architectural Principle

**Context Retrieval is a separate domain concern from artifact/relation storage.**

This service must be:
1. **Isolated**: Own module/service, not embedded in artifact_service
2. **Policy-driven**: Configurable rules for context assembly
3. **Extensible**: Support future context strategies without API changes

### Domain Concepts

#### Context Policy
A policy defines how context is assembled for an artifact. Initial policies:

| Policy | Description |
|--------|-------------|
| `direct_relations` | Include artifacts directly connected by any relation |
| `derived_lineage` | Include source and all derived artifacts (follow `derived_from` chain) |
| `evidence_chain` | Include supporting evidence (follow `supports` chain) |
| `full_graph` | All connected artifacts within N hops |

Policies should be composable and stored as configuration (not hardcoded).

#### Context Response
The response structure must clearly separate:
- **Primary artifact**: The requested artifact
- **Context artifacts**: Related artifacts with relationship metadata
- **Policy applied**: Which policy generated this context

### Requirements

**Endpoint**: `POST /context/{artifact_id}` (POST to support request body)

**Query Parameters**:
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `policy` | string | `derived_lineage` | Context assembly policy |
| `depth` | integer | 1 | Max traversal depth (for graph policies) |
| `types` | string[] | null | Filter context artifacts by type |
| `include_content` | boolean | true | Include artifact content in response |

**Request Body** (optional): `ContextHints`

The request body allows clients to pass metadata that influences context assembly. This enables "smart" context generation tailored to the specific use case.

```
ContextHints:
  query: string | null              # The prompt/question driving this request
  task_type: string | null          # Intent: "qa", "summarization", "analysis", "comparison"
  token_budget: integer | null      # Max tokens for context (forces prioritization)
  temporal_focus: TemporalHint | null
  relevance_threshold: float | null # 0.0-1.0, filter by semantic relevance to query
  exclusions: UUID[] | null         # Artifacts to explicitly exclude
  preferences: ContextPreferences | null

TemporalHint:
  mode: "recent" | "historical" | "range"
  days_back: integer | null         # For "recent" mode
  start_date: date | null           # For "range" mode
  end_date: date | null

ContextPreferences:
  artifact_types: TypePriority[] | null    # Prioritize certain types
  source_systems: string[] | null          # Prefer certain sources
  min_confidence: float | null             # Relation confidence threshold
  prefer_recent: boolean | null            # Recency bias
```

**Example Request Bodies**:

1. **Question-Answering Context**:
```json
{
  "query": "What are the key security considerations?",
  "task_type": "qa",
  "token_budget": 4000,
  "preferences": {
    "artifact_types": [
      {"type": "finding", "priority": 1},
      {"type": "analysis", "priority": 2}
    ]
  }
}
```

2. **Summary Generation Context**:
```json
{
  "task_type": "summarization",
  "token_budget": 8000,
  "temporal_focus": {
    "mode": "recent",
    "days_back": 30
  }
}
```

3. **Comparison Context**:
```json
{
  "task_type": "comparison",
  "query": "Compare PostgreSQL vs MongoDB approaches",
  "relevance_threshold": 0.7
}
```

**Response Structure** (schema design, not code):
```
ContextResponse:
  artifact: ArtifactResponse           # The primary artifact
  context: ContextArtifact[]          # Related artifacts with metadata
  policy: string                       # Policy that was applied
  hints_applied: ContextHintsApplied  # Summary of how hints affected results
  metadata:
    depth_used: integer               # Actual traversal depth
    artifact_count: integer           # Total artifacts in context
    tokens_estimated: integer | null  # If token_budget was set
    artifacts_excluded: integer       # Count of artifacts filtered out

ContextArtifact:
  artifact: ArtifactResponse          # The context artifact
  relation_path: RelationPathItem[]   # How this artifact relates to primary
  distance: integer                   # Hops from primary artifact
  relevance_score: float | null       # If query was provided (0.0-1.0)
  inclusion_reason: string            # Why this artifact was included

RelationPathItem:
  relation_type: string               # e.g., "derived_from"
  direction: "outgoing" | "incoming"  # From perspective of path traversal

ContextHintsApplied:
  query_provided: boolean
  token_budget_enforced: boolean
  temporal_filter_applied: boolean
  relevance_filtering_applied: boolean
  exclusions_applied: integer
```

### Acceptance Criteria
1. Single request retrieves artifact + all relevant context
2. Policy determines what "relevant" means
3. Depth parameter limits graph traversal
4. Type filtering reduces response size
5. Response includes relationship path for each context artifact
6. Tenant isolation enforced throughout traversal
7. Performance: <200ms for typical document with 10 related artifacts
8. **Hints processing**:
   - Query hint enables semantic relevance scoring of context artifacts
   - Token budget enforces prioritized truncation
   - Temporal hints filter by artifact creation date
   - Exclusions are respected before any other filtering
   - All applied hints are reflected in response metadata

### Architectural Requirements

1. **Separate Service Layer**
   - Create `context_service.py` (not methods in artifact_service)
   - Service owns all policy logic and graph traversal

2. **Policy Configuration**
   - Policies defined in configuration (YAML or database)
   - Support adding new policies without code changes
   - Each policy specifies: relation types to follow, direction, max depth

3. **No Business Logic in Router**
   - Router only handles HTTP concerns
   - All context assembly logic in service layer

4. **Graph Traversal**
   - Use iterative approach (not recursive SQL)
   - Track visited nodes to prevent cycles
   - Respect depth limits strictly

5. **Caching Consideration**
   - Context is computed, not stored
   - Consider caching at service layer for frequently-accessed documents
   - Cache invalidation on relation changes
   - Note: Hints make caching complex—consider caching unhinted base context only

6. **Hints Processing Pipeline**
   - Hints should be processed as a pipeline of filters/transformers
   - Each hint type has a dedicated processor
   - Processors are applied in deterministic order:
     1. Exclusions (remove specified artifacts)
     2. Temporal filtering (remove outside date range)
     3. Type preferences (adjust scoring)
     4. Relevance scoring (if query provided, compute similarity)
     5. Token budget (truncate lowest-scored items)
   - New hint types can be added by implementing new processors

7. **Relevance Scoring (Query Hint)**
   - When query is provided, compute semantic similarity between query and each context artifact
   - Requires embedding lookup or on-the-fly embedding generation
   - Use existing embedding infrastructure
   - Cache query embedding for duration of request

### Future Extensions (Do Not Implement Now)
- User-defined policies via API
- Policy composition (combine multiple policies)
- Streaming response for large contexts
- LLM-assisted context selection (use LLM to judge relevance)
- Context explanation (natural language description of why each artifact is included)

---

## P2: Relation-Aware Search Filters

### Problem Statement
Current search endpoints find artifacts by content similarity but cannot filter based on relationship structure. Use cases like "find all summaries derived from documents about PostgreSQL" require post-search filtering.

### Requirements

**Affected Endpoints**: 
- `POST /search/semantic`
- `POST /search/hybrid`
- `GET /search/fulltext`

**New Query Parameters**:

| Parameter | Type | Description |
|-----------|------|-------------|
| `related_to` | UUID | Only return artifacts related to this artifact |
| `relation_type` | string | Filter by relation type when `related_to` is set |
| `relation_direction` | string | `incoming`, `outgoing`, or `both` |

**Behavior**:
- When `related_to` is set, results are filtered to artifacts that have a relation to/from the specified artifact
- Search scoring remains unchanged; relation filter is post-search
- Can combine with existing `artifact_types` filter

### Acceptance Criteria
1. Search returns only related artifacts when filter is applied
2. Performance impact <20% compared to unfiltered search
3. Relation filter works with all search modes (semantic, fulltext, hybrid)

### Implementation Notes
- Consider using subquery or JOIN approach
- For semantic search, may need to filter after vector similarity calculation
- Index on relation source_id and target_id should already exist

---

## P3: Graph Traversal Queries (Future)

### Problem Statement
Complex queries like "what documents support decisions that resolve intents created this week" require multi-hop graph traversal with filtering.

### Deferred
This enhancement is deferred pending:
1. Validation of P1 context retrieval
2. Clear use cases from production usage
3. Evaluation of dedicated graph query language vs. REST API

### Preliminary Concepts
- Path-based query syntax
- Cypher-like DSL or GraphQL integration
- Recursive CTE optimization for PostgreSQL

---

## Implementation Sequence

```
Phase 1: Foundation (Week 1)
├── P0: Batch Artifact Retrieval
│   └── Extend existing endpoint, low risk
└── P1: Context Service Setup
    └── Create service module, define policy schema

Phase 2: Context Retrieval (Week 2-3)
├── P1: Policy Implementation
│   ├── derived_lineage policy
│   └── direct_relations policy
├── P1: Context Endpoint
│   └── Router, schemas, tests
└── P1: Performance Validation
    └── Load testing, optimization

Phase 3: Search Enhancement (Week 4)
└── P2: Relation-Aware Search
    └── Add filters to existing endpoints
```

---

## Testing Requirements

### P0: Batch Retrieval
- Unit tests: ID parsing, ordering, deduplication
- Integration tests: Multi-tenant isolation, missing IDs handling
- Performance tests: 100-artifact batch under load

### P1: Context Retrieval
- Unit tests: Each policy's traversal logic independently
- Integration tests: 
  - Cycle detection
  - Depth limiting
  - Multi-tenant isolation in traversal
  - Large context handling (50+ artifacts)
- Property-based tests: Policy composition produces valid subgraphs

### P2: Search Filters
- Unit tests: Filter query construction
- Integration tests: Combined filters with search scoring
- Performance tests: Filter overhead measurement

---

## Schema Changes

### Required: None
All enhancements work with existing database schema.

### Recommended: Context Policy Table (P1)

If dynamic policy configuration is desired:

**Table**: `mimirdata.context_policy`

| Column | Type | Description |
|--------|------|-------------|
| code | TEXT PK | Policy identifier |
| name | TEXT | Human-readable name |
| description | TEXT | Policy documentation |
| config | JSONB | Policy parameters |
| is_default | BOOLEAN | Default policy flag |
| created_at | TIMESTAMPTZ | |

This is optional—policies can alternatively be defined in application configuration.

---

## Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Context retrieval latency | <200ms p95 | APM monitoring |
| API calls for RAG context | 1-2 (down from N+1) | Client telemetry |
| Search filter overhead | <20% | A/B latency comparison |
| Batch retrieval throughput | 100 artifacts <50ms | Load testing |

---

## Reference Documents

- `docs/architecture.md` - System architecture
- `docs/api-design.md` - API design principles  
- `docs/data-model.md` - Entity relationships
- `tools/validation-scenarios/docs/requirements.md` - Validation tool requirements
- `tools/validation-scenarios/docs/api-assessment.md` - Detailed API analysis