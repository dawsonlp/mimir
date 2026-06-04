# API Design Assessment for RAG Use Cases

## Current Status

This assessment was written against the older V2 API shape. It is useful
historical input, but it is not current for Mimir v5.5. The current validation
roadmap should reassess the API around:

- `mimir-client` tenant shortname behavior;
- unified `POST /search`;
- graph-scoped search;
- graph-based context retrieval;
- provenance APIs;
- embedding type/vector behavior;
- change outbox and Kafka publisher semantics.

## Executive Summary

The historical Mímir V2 API was **well-designed for the core storage model**
(artifacts, relations, embeddings) but had **gaps for efficient RAG context
retrieval**. Those gaps were later addressed by graph traversal and context
service work; this document should be refreshed before it is used for current
planning.

**Verdict**: Good foundation, needs 2-3 enhancements for production RAG workloads.

---

## Strengths

### 1. Unified Artifact Model ✓
Everything is an artifact with type discrimination (`document`, `analysis`, `summary`, `finding`, etc.). This is ideal for storing diverse knowledge types uniformly.

```
Artifact Types:
├── Content: document, conversation, note
├── Positional: chunk, quote, highlight, annotation  
└── Derived: analysis, summary, finding, question, answer
```

### 2. Flexible Relations ✓
- `derived_from` / `source_of` - Perfect for linking analyses to source documents
- `supports` / `supported_by` - Good for evidence chains
- `references` / `referenced_by` - Citation tracking
- Bidirectional querying via `as_source` and `as_target` parameters

### 3. Client-Generated UUIDs ✓
Optional UUIDv7 support enables:
- Idempotent requests (retry-safe)
- Client-side ID generation for batching
- Time-ordered IDs for natural sorting

### 4. Extensible Metadata ✓
JSONB metadata on artifacts and relations allows storing:
- LLM model used for analysis
- Perspective name
- Generation parameters
- Confidence scores

### 5. Multi-Modal Search ✓
- Full-text search (tsvector)
- Semantic search (pgvector)
- Hybrid search (RRF algorithm)
- Similar artifacts by embedding

### 6. Provenance Tracking ✓
Automatic audit trail with actor types (`user`, `system`, `llm`, `api_client`) - essential for tracking LLM-generated content.

---

## Gaps for RAG Use Case

### Gap 1: N+1 Query Problem (HIGH PRIORITY)

**Problem**: To build context for a document, client must:
1. `GET /artifacts/{doc_id}` - Get document
2. `GET /relations/artifact/{doc_id}` - Get relations (returns IDs only)
3. `GET /artifacts/{analysis1_id}` - Get first analysis
4. `GET /artifacts/{analysis2_id}` - Get second analysis
5. ... repeat for N analyses

**Impact**: 5 perspectives = 7 API calls minimum. This is unacceptable latency for real-time RAG.

**Recommended Solutions**:

A. **Add context expansion endpoint** (RECOMMENDED):
```
GET /artifacts/{id}/context?expand=relations&direction=incoming&types=derived_from
```
Returns:
```json
{
  "artifact": { "id": "...", "content": "..." },
  "related": [
    { "relation": { "type": "derived_from", ... }, 
      "artifact": { "id": "...", "type": "analysis", "content": "..." }}
  ]
}
```

B. **Add batch retrieval**:
```
GET /artifacts?ids=uuid1,uuid2,uuid3
```

C. **Expand relations in artifact response**:
```
GET /artifacts/{id}?expand=derived_from
```

### Gap 2: No Relation-Aware Search (MEDIUM PRIORITY)

**Problem**: Cannot search for "all analyses derived from documents about PostgreSQL".

**Current workaround**: 
1. Search for documents matching "PostgreSQL"
2. For each result, query relations
3. Filter manually

**Recommended Solution**:
```
POST /search/semantic
{
  "query": "PostgreSQL best practices",
  "relation_filter": {
    "direction": "sources",
    "type": "derived_from",
    "artifact_type": "document"
  }
}
```

### Gap 3: No Transitive Relation Traversal (LOW PRIORITY)

**Problem**: Can't answer "what documents support decisions that resolve this intent?"

**Current workaround**: Multiple API calls with client-side graph traversal.

**Recommended Solution**: GraphQL-like query or dedicated endpoint:
```
GET /graph/traverse?start={id}&path=supports.resolves&depth=2
```

---

## Workarounds for Current Implementation

### Building RAG Context (Efficient Approach)

```python
async def get_document_context(client: MimirClient, doc_id: UUID) -> dict:
    """Build RAG context with current API (minimized calls)."""
    
    # 1. Get document + relations in parallel
    doc, relations = await asyncio.gather(
        client.get_artifact(doc_id),
        client.get_artifact_relations(doc_id, as_target=True)  # Get sources
    )
    
    # 2. Extract related artifact IDs
    related_ids = [r.source_id for r in relations if r.relation_type == "derived_from"]
    
    # 3. Batch fetch related artifacts (if endpoint exists) or parallel fetch
    related_artifacts = await asyncio.gather(
        *[client.get_artifact(aid) for aid in related_ids]
    )
    
    # 4. Organize by type
    context = {
        "document": doc,
        "analyses": [a for a in related_artifacts if a.artifact_type == "analysis"],
        "summaries": [a for a in related_artifacts if a.artifact_type == "summary"],
        "findings": [a for a in related_artifacts if a.artifact_type == "finding"],
    }
    
    return context
```

**Latency**: ~2 + N API calls with asyncio parallelism

### Recommended API Endpoint Addition

For the validation tool to work efficiently, I recommend adding ONE endpoint:

```python
# backend/src/mimir/routers/artifacts.py

@router.get("/{artifact_id}/context")
async def get_artifact_with_context(
    artifact_id: UUID,
    x_tenant_id: int = Header(...),
    relation_types: list[str] = Query(None),
    direction: str = Query("both", regex="^(incoming|outgoing|both)$"),
    include_content: bool = Query(True),
) -> dict:
    """Get artifact with all related artifacts for RAG context building."""
    ...
```

---

## Assessment Summary

| Aspect | Rating | Notes |
|--------|--------|-------|
| Data Model | ★★★★★ | Unified artifacts, flexible types |
| Relations API | ★★★★☆ | Good queries, missing batch/expand |
| Search API | ★★★★☆ | Multi-modal, missing relation filters |
| RAG Support | ★★★☆☆ | Requires N+1 queries for context |
| Provenance | ★★★★★ | Excellent audit trail |
| Extensibility | ★★★★★ | JSONB metadata, custom types |

**Overall**: 4/5 - Ready for development, needs one endpoint for production efficiency.

---

## Recommendation

**Proceed with validation tool implementation** using current API with parallel fetching workaround. Document the need for:

1. `GET /artifacts/{id}/context` endpoint (CRITICAL for v1.0)
2. Batch artifact retrieval (IMPORTANT)
3. Relation-aware search (NICE TO HAVE)

The current API is sufficient to validate the end-to-end scenario; efficiency optimizations can follow.
