# Mímir Semantic Layer - Design Document

## Overview

The Mímir Semantic Layer is a Python client library that provides intelligent context assembly and semantic operations built on top of the Mímir Storage API. It maintains strict separation between storage primitives (artifacts, relations, embeddings) and semantic interpretation (context, lineage, relevance).

---

## Architecture

### Layer Separation

```
┌─────────────────────────────────────────────────────────────┐
│                    Application Layer                         │
│  RAG pipelines, chat applications, analysis tools            │
│  Uses mimir_semantic to compose intelligent context          │
└──────────────────────────┬──────────────────────────────────┘
                           │ Python imports
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                   Semantic Layer                             │
│  mimir_semantic package                                      │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────────────┐   │
│  │   Client    │ │   Context   │ │       Search        │   │
│  │  (REST)     │ │  Assembly   │ │  (semantic/hybrid)  │   │
│  └─────────────┘ └─────────────┘ └─────────────────────┘   │
│  Understands meaning, composes primitives, manages tokens   │
└──────────────────────────┬──────────────────────────────────┘
                           │ HTTP/REST (only path)
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                    Storage Layer                             │
│  Mímir Backend API (http://localhost:38000)                  │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌───────────────┐  │
│  │Artifacts │ │Relations │ │Embeddings│ │  Provenance   │  │
│  └──────────┘ └──────────┘ └──────────┘ └───────────────┘  │
│  Pure storage, no interpretation, stable API contract       │
└─────────────────────────────────────────────────────────────┘
```

### Key Constraint

**The Semantic Layer ONLY communicates with the Storage Layer via REST API.**

This constraint ensures:
1. Clean architectural boundary
2. Storage layer can evolve independently
3. Semantic layer could be moved to a separate service
4. No temptation to bypass the API for "optimization"

---

## Core Components

### 1. MimirClient

The primary interface for all storage operations. Wraps the REST API with Pythonic methods.

```python
class MimirClient:
    """Client for Mímir Storage API.
    
    All storage operations go through this client. It provides:
    - Typed Python methods for all API endpoints
    - Automatic tenant ID header injection
    - Documentation links in every method
    - Connection pooling via httpx
    """
    
    def __init__(
        self,
        base_url: str = "http://localhost:38000",
        docs_url: str | None = None,
        tenant_id: int | None = None,
    ): ...
    
    # Artifact operations
    async def create_artifact(...) -> Artifact
    async def get_artifact(...) -> Artifact
    async def list_artifacts(...) -> ArtifactList
    
    # Relation operations
    async def create_relation(...) -> Relation
    async def get_relations(...) -> RelationList
    
    # Embedding operations
    async def create_embedding(...) -> Embedding
    async def find_similar(...) -> SimilarityResults
    
    # Search operations
    async def semantic_search(...) -> SearchResults
    async def fulltext_search(...) -> SearchResults
    async def hybrid_search(...) -> SearchResults
```

### 2. Context Assembly

High-level operations for gathering relevant context.

```python
class ContextAssembler:
    """Assembles context from multiple artifacts based on policies."""
    
    async def gather_context(
        artifact_id: UUID,
        depth: int = 2,
        policy: ContextPolicy = "derived_lineage",
        token_budget: int | None = None,
        include_types: list[str] | None = None,
        exclude_types: list[str] | None = None,
    ) -> EnrichedContext: ...
    
    async def gather_for_query(
        query: str,
        query_vector: list[float],
        limit: int = 10,
        token_budget: int | None = None,
    ) -> EnrichedContext: ...
```

### 3. Token Budgeting

Manages context size for LLM prompts.

```python
class TokenBudget:
    """Manages token allocation for context windows."""
    
    def __init__(self, budget: int, model: str = "gpt-4"):
        self.budget = budget
        self.tokenizer = get_tokenizer(model)
    
    def estimate_tokens(self, text: str) -> int: ...
    def can_fit(self, text: str) -> bool: ...
    def allocate(self, artifacts: list[Artifact]) -> list[Artifact]: ...
```

---

## Design Decisions

### D1: REST-Only Communication

**Decision**: The semantic layer never accesses the database directly.

**Rationale**:
- Clean architectural boundary
- Storage API becomes the contract
- Enables independent evolution
- Could deploy semantic layer as separate service

**Consequence**: Some operations may require multiple API calls. If this becomes a performance issue, we request API enhancements rather than bypassing the API.

### D2: Documentation-Transparent Docstrings

**Decision**: Every client method documents the underlying API endpoint.

**Rationale**:
- Developers can see exactly what API calls happen
- Easy to debug by reproducing in curl
- API documentation is single source of truth
- Helps identify when API enhancements are needed

**Implementation**:
```python
async def create_artifact(self, ...) -> Artifact:
    """Create a new artifact.
    
    API Reference
    -------------
    POST /artifacts
    See: {docs_url}#/Artifacts/create_artifact_artifacts_post
    
    Request Headers:
        X-Tenant-ID: {tenant_id}
    
    ...
    """
```

### D3: Configurable URLs

**Decision**: API and documentation URLs are configurable.

**Rationale**:
- Development uses localhost
- Production uses deployed URLs
- Documentation may be hosted separately

**Configuration Sources**:
1. Constructor arguments
2. Environment variables (MIMIR_API_URL, MIMIR_DOCS_URL)
3. `.env` file

### D4: Async-First

**Decision**: All client methods are async.

**Rationale**:
- HTTP operations are I/O bound
- Enables concurrent requests
- Matches modern Python async patterns
- Can gather multiple artifacts in parallel

**Synchronous Wrapper** (if needed):
```python
def sync_get_artifact(self, artifact_id: UUID) -> Artifact:
    """Synchronous wrapper for get_artifact."""
    return asyncio.run(self.get_artifact(artifact_id))
```

### D5: Pydantic Models Mirror API Schemas

**Decision**: Client uses Pydantic models that match API response schemas.

**Rationale**:
- Type safety
- IDE autocomplete
- Validation on response parsing
- Documentation generation

**Synchronization**: Models are manually maintained to match API. Future enhancement could auto-generate from OpenAPI spec.

---

## API Request Process

When the semantic layer needs functionality not available in the Storage API:

1. **Document the need** in `docs/api-requests.md`
2. **Implement workaround** using existing endpoints
3. **Propose API enhancement** to storage team
4. **Update client** when enhancement is released

Example:

```markdown
# docs/api-requests.md

## Request: GET /artifacts/{id}/lineage

**Date**: 2026-02-01
**Status**: Proposed

### Need
Retrieve full provenance chain from artifact to its sources.

### Current Workaround
Multiple calls to /relations + /artifacts, traversing manually.

### Proposed Endpoint
GET /artifacts/{id}/lineage?depth=3

### Response
{
  "artifact": {...},
  "lineage": [
    {"artifact": {...}, "relation_type": "derived_from", "depth": 1},
    ...
  ]
}

### Priority
Medium - current workaround works but inefficient for deep lineage.
```

---

## Testing Strategy

### Unit Tests
- Mock httpx responses
- Test client method parsing
- Test token budgeting logic

### Integration Tests
- Require running Mímir API
- Test full workflows
- Marked with `@pytest.mark.integration`

### Test Fixtures
```python
@pytest.fixture
async def client():
    """Provides configured client for tests."""
    client = MimirClient.from_env()
    yield client
    await client.close()

@pytest.fixture
async def test_tenant(client):
    """Creates a test tenant, cleans up after."""
    tenant = await client.create_tenant(
        shortname=f"test-{uuid4().hex[:8]}",
        name="Test Tenant",
    )
    yield tenant
    # Tenant persists (append-only), no cleanup needed
```

---

## Package Structure

```
semantic/
├── pyproject.toml
├── README.md
├── docs/
│   ├── design.md           # This document
│   └── api-requests.md     # Requested API enhancements
├── src/
│   └── mimir_semantic/
│       ├── __init__.py     # Package exports
│       ├── client.py       # MimirClient
│       ├── config.py       # Settings, environment loading
│       ├── models.py       # Pydantic models
│       ├── exceptions.py   # Custom exceptions
│       ├── context/
│       │   ├── __init__.py
│       │   ├── assembler.py    # ContextAssembler
│       │   ├── policies.py     # Context inclusion policies
│       │   └── budgeting.py    # Token budget management
│       └── search/
│           ├── __init__.py
│           ├── semantic.py     # Semantic search helpers
│           └── hybrid.py       # Hybrid search helpers
└── tests/
    ├── conftest.py
    ├── test_client.py
    ├── test_models.py
    └── integration/
        ├── test_artifacts.py
        └── test_context.py
```

---

## Future Considerations

### F1: OpenAPI Code Generation
Could auto-generate client methods and models from OpenAPI spec. Pros: always in sync. Cons: less readable, harder to add semantic methods.

### F2: Caching Layer
Could cache artifact lookups. Must be careful with cache invalidation since we don't control when storage changes.

### F3: Streaming Support
For large context assembly, could stream results. Requires API support for streaming responses.

### F4: GraphQL Gateway
Could expose semantic operations as GraphQL. Natural fit for graph traversal queries.

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 0.1.0 | 2026-02-02 | Initial design |