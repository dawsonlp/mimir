"""Search API endpoints (V2).

Mímir provides multiple search strategies optimized for different scenarios. 
Understanding when to use each approach is key to building effective RAG applications.

## Choosing a Search Strategy

| Scenario | Recommended Endpoint | Why |
|----------|---------------------|-----|
| User typed a question/query | `/search/fulltext` | Fast, keyword-based, no embedding needed |
| Semantic similarity (find "like this") | `/search/semantic` | Finds conceptually similar content |
| Best of both worlds | `/search/hybrid` | Combines keyword matching with semantic understanding |
| "More like this" exploration | `/search/similar/{id}` | Find related artifacts from a known starting point |

## Relation-Aware Filtering

All search endpoints support filtering by relationship structure. This is powerful for 
graph-constrained retrieval - finding content that is both relevant AND structurally 
connected to a specific artifact.

**Common patterns:**
- Find all decisions derived from a specific document
- Search notes that reference a particular analysis  
- Retrieve summaries connected to a conversation thread
"""

from uuid import UUID

from fastapi import APIRouter, Header, Query

from mimir.schemas.search import SearchResponse
from mimir.services import search_service
from mimir.services.search_service import RelationDirection

router = APIRouter(prefix="/search", tags=["search"])


# ============================================================================
# FULL-TEXT SEARCH
# ============================================================================

@router.get("/fulltext", response_model=SearchResponse)
async def fulltext_search(
    query: str = Query(..., description="Search text - uses PostgreSQL full-text search"),
    x_tenant_id: int = Header(..., alias="X-Tenant-ID"),
    artifact_types: list[str] | None = Query(
        None,
        description="Filter by artifact types (e.g., 'decision', 'summary', 'note')",
    ),
    limit: int = Query(20, ge=1, le=100, description="Maximum results to return"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    related_to: UUID | None = Query(
        None,
        description="Only return artifacts related to this artifact UUID (graph filter)",
    ),
    relation_type: str | None = Query(
        None,
        description="Filter by relation type (e.g., 'derived_from', 'supports'). Requires related_to.",
    ),
    relation_direction: RelationDirection = Query(
        RelationDirection.BOTH,
        description="Which relations to consider: 'incoming', 'outgoing', or 'both'",
    ),
) -> SearchResponse:
    """Full-text search using PostgreSQL FTS - fast keyword-based retrieval.
    
    ## When to Use Full-Text Search
    
    **Best for:**
    - User-typed queries where exact words matter
    - Finding artifacts containing specific technical terms
    - Quick lookups when you don't have embeddings ready
    - Scenarios where speed is critical (no vector computation)
    
    **Examples:**
    - "Find all artifacts mentioning PostgreSQL configuration"
    - "Search for decisions about authentication"
    - "Look up notes containing 'security vulnerability'"
    
    ## How It Works
    
    Uses PostgreSQL's built-in full-text search with English stemming and ranking.
    Results are ranked by relevance based on term frequency and document structure.
    Title matches are weighted higher than content matches.
    
    ## Compared to Semantic Search
    
    | Aspect | Full-Text | Semantic |
    |--------|-----------|----------|
    | Speed | ⚡ Very fast | Slower (embedding lookup) |
    | Exact terms | ✅ Finds exact matches | May miss exact terms |
    | Concepts | ❌ Keyword only | ✅ Understands meaning |
    | Setup | No embedding needed | Requires pre-computed embeddings |
    
    ## Relation-Aware Filtering (Optional)
    
    Add `related_to` to constrain results to artifacts connected in the knowledge graph.
    
    **Scenario:** "Find notes about PostgreSQL that are derived from my architecture document"
    ```
    GET /search/fulltext?query=PostgreSQL&related_to={doc_uuid}&relation_type=derived_from
    ```
    
    **Understanding directions:**
    - `incoming`: Artifacts that point TO the anchor (e.g., summaries derived FROM a document)
    - `outgoing`: Artifacts that the anchor points TO (e.g., sources a decision references)
    - `both`: Either direction (default)
    
    The anchor artifact itself is never included in results.
    """
    # Fetch more results when filtering, to account for post-filter reduction
    fetch_limit = limit * 3 if related_to else limit
    
    response = await search_service.fulltext_search(
        x_tenant_id, query, artifact_types, fetch_limit, offset
    )
    
    # Apply relation filter post-search (preserves search scoring)
    if related_to:
        related_ids = await search_service.get_related_artifact_ids(
            x_tenant_id, related_to, relation_type, relation_direction
        )
        filtered = search_service._filter_results_by_relation(response.results, related_ids)
        return SearchResponse(
            results=filtered[:limit],
            total=len(filtered),
            query=response.query,
        )
    
    return response


# ============================================================================
# SEMANTIC SEARCH
# ============================================================================

@router.post("/semantic", response_model=SearchResponse)
async def semantic_search(
    query_vector: list[float],
    x_tenant_id: int = Header(..., alias="X-Tenant-ID"),
    artifact_types: list[str] | None = Query(
        None,
        description="Filter by artifact types (e.g., 'decision', 'summary', 'note')",
    ),
    limit: int = Query(20, ge=1, le=100, description="Maximum results to return"),
    similarity_threshold: float = Query(
        0.0, ge=0.0, le=1.0,
        description="Minimum similarity score (0.0-1.0). Higher = more selective.",
    ),
    model: str | None = Query(
        None,
        description="Embedding model to query against (e.g., 'text-embedding-3-small')",
    ),
    related_to: UUID | None = Query(
        None,
        description="Only return artifacts related to this artifact UUID (graph filter)",
    ),
    relation_type: str | None = Query(
        None,
        description="Filter by relation type (e.g., 'derived_from', 'supports'). Requires related_to.",
    ),
    relation_direction: RelationDirection = Query(
        RelationDirection.BOTH,
        description="Which relations to consider: 'incoming', 'outgoing', or 'both'",
    ),
) -> SearchResponse:
    """Semantic search using vector similarity - find conceptually related content.
    
    ## When to Use Semantic Search
    
    **Best for:**
    - Finding content "about" a concept even without exact keywords
    - RAG retrieval where you need contextually relevant content
    - Queries like "similar to this idea" or "related concepts"
    - When user intent matters more than exact wording
    
    **Examples:**
    - Find content about "database performance" (matches "PostgreSQL optimization", "query tuning")
    - Retrieve context for an LLM prompt about a specific topic
    - Find decisions related to a concept even if terminology varies
    
    ## How It Works
    
    1. **You provide** a query embedding vector (from your embedding model)
    2. **Mímir compares** it against pre-stored artifact embeddings using cosine similarity
    3. **Results ranked** by similarity score (1.0 = identical, 0.0 = unrelated)
    
    **Important:** Artifacts must have embeddings created via `/embeddings` endpoint first.
    
    ## Request Body
    
    Send the query embedding as a JSON array of floats:
    ```json
    [0.023, -0.041, 0.089, ...]  // 1536 dimensions for OpenAI text-embedding-3-small
    ```
    
    ## Similarity Threshold
    
    Use `similarity_threshold` to filter out low-quality matches:
    - `0.7+`: High confidence matches (recommended for RAG)
    - `0.5-0.7`: Moderate relevance
    - `<0.5`: Loosely related (may include noise)
    
    ## Compared to Full-Text Search
    
    | Scenario | Use Full-Text | Use Semantic |
    |----------|---------------|--------------|
    | "Find docs mentioning PostgreSQL" | ✅ | ❌ |
    | "Find docs about databases" | ❌ | ✅ |
    | User types exact error message | ✅ | ❌ |
    | Find similar architectural decisions | ❌ | ✅ |
    
    ## Relation-Aware Filtering (Optional)
    
    Combine semantic similarity with graph structure for precise retrieval.
    
    **Scenario:** "Find semantically similar content within a document's lineage"
    ```
    POST /search/semantic?related_to={doc_uuid}&relation_direction=incoming
    Body: [embedding vector]
    ```
    
    This finds content that is both semantically similar to your query AND structurally 
    connected to the anchor artifact.
    """
    # Fetch more results when filtering, to account for post-filter reduction
    fetch_limit = limit * 3 if related_to else limit
    
    response = await search_service.semantic_search(
        x_tenant_id,
        query_vector,
        artifact_types,
        fetch_limit,
        similarity_threshold,
        model,
    )
    
    # Apply relation filter post-search (preserves search scoring)
    if related_to:
        related_ids = await search_service.get_related_artifact_ids(
            x_tenant_id, related_to, relation_type, relation_direction
        )
        filtered = search_service._filter_results_by_relation(response.results, related_ids)
        return SearchResponse(
            results=filtered[:limit],
            total=len(filtered),
            query=response.query,
        )
    
    return response


# ============================================================================
# HYBRID SEARCH
# ============================================================================

@router.post("/hybrid", response_model=SearchResponse)
async def hybrid_search(
    query: str = Query(..., description="Search text for full-text matching"),
    query_vector: list[float] = ...,
    x_tenant_id: int = Header(..., alias="X-Tenant-ID"),
    artifact_types: list[str] | None = Query(
        None,
        description="Filter by artifact types (e.g., 'decision', 'summary', 'note')",
    ),
    limit: int = Query(20, ge=1, le=100, description="Maximum results to return"),
    rrf_k: int = Query(
        60, ge=1,
        description="RRF constant. Higher = less aggressive rank fusion (60 is standard).",
    ),
    semantic_weight: float = Query(
        0.5, ge=0.0, le=1.0,
        description="Balance between semantic (1.0) and fulltext (0.0). Default 0.5 = equal.",
    ),
    model: str | None = Query(
        None,
        description="Embedding model to query against (e.g., 'text-embedding-3-small')",
    ),
    related_to: UUID | None = Query(
        None,
        description="Only return artifacts related to this artifact UUID (graph filter)",
    ),
    relation_type: str | None = Query(
        None,
        description="Filter by relation type (e.g., 'derived_from', 'supports'). Requires related_to.",
    ),
    relation_direction: RelationDirection = Query(
        RelationDirection.BOTH,
        description="Which relations to consider: 'incoming', 'outgoing', or 'both'",
    ),
) -> SearchResponse:
    """Hybrid search combining full-text and semantic search with Reciprocal Rank Fusion.
    
    ## When to Use Hybrid Search
    
    **Best for:**
    - Production RAG applications where you want the best of both worlds
    - Queries where both exact terms AND conceptual similarity matter
    - When you're not sure if fulltext or semantic will work better
    - Building robust retrieval that handles diverse query types
    
    **Examples:**
    - "PostgreSQL performance optimization" - matches keyword "PostgreSQL" AND concept "performance"
    - RAG context retrieval where you want comprehensive coverage
    - Enterprise search where users have varying query styles
    
    ## How It Works
    
    1. Runs full-text search on your query text
    2. Runs semantic search on your query embedding
    3. Combines results using **Reciprocal Rank Fusion (RRF)**
    4. RRF merges rankings without needing to normalize different score types
    
    **RRF Formula:** `score = Σ 1/(k + rank)`
    
    This elegantly combines rankings from different sources without comparing raw scores.
    
    ## Request Body
    
    Send the query embedding as a JSON array of floats:
    ```json
    [0.023, -0.041, 0.089, ...]
    ```
    
    ## Tuning the Balance
    
    Use `semantic_weight` to control the balance:
    
    | Weight | Behavior | Best For |
    |--------|----------|----------|
    | `0.0` | 100% fulltext | Technical docs, exact term search |
    | `0.3` | Keyword-heavy | Known terminology, specific searches |
    | `0.5` | Balanced (default) | General purpose, mixed queries |
    | `0.7` | Semantic-heavy | Conceptual queries, exploration |
    | `1.0` | 100% semantic | "Find similar" queries |
    
    ## The RRF Constant (rrf_k)
    
    The `rrf_k` parameter (default 60) controls ranking aggression:
    - **Lower values** (20-40): Top results dominate more
    - **Higher values** (60-100): More democratic, spreads influence
    - **60** is the standard value from academic literature
    
    Most applications should leave this at default unless tuning for specific behavior.
    
    ## Relation-Aware Filtering (Optional)
    
    **Scenario:** "Find the best content about security within this project's document graph"
    ```
    POST /search/hybrid?query=security%20best%20practices&related_to={project_uuid}
    Body: [embedding vector]
    ```
    
    The relation filter is applied AFTER hybrid scoring, so you get the best-ranked 
    results that also satisfy the graph constraint.
    """
    # Fetch more results when filtering, to account for post-filter reduction
    fetch_limit = limit * 3 if related_to else limit
    
    response = await search_service.hybrid_search(
        x_tenant_id,
        query,
        query_vector,
        artifact_types,
        fetch_limit,
        rrf_k,
        semantic_weight,
        model,
    )
    
    # Apply relation filter post-search (preserves search scoring)
    if related_to:
        related_ids = await search_service.get_related_artifact_ids(
            x_tenant_id, related_to, relation_type, relation_direction
        )
        filtered = search_service._filter_results_by_relation(response.results, related_ids)
        return SearchResponse(
            results=filtered[:limit],
            total=len(filtered),
            query=response.query,
        )
    
    return response


# ============================================================================
# SIMILARITY SEARCH
# ============================================================================

@router.get("/similar/{artifact_id}", response_model=SearchResponse)
async def similar_artifacts(
    artifact_id: UUID,
    x_tenant_id: int = Header(..., alias="X-Tenant-ID"),
    limit: int = Query(10, ge=1, le=50, description="Maximum results to return"),
    artifact_types: list[str] | None = Query(
        None,
        description="Filter by artifact types (e.g., 'decision', 'summary', 'note')",
    ),
    model: str | None = Query(
        None,
        description="Embedding model to use for similarity comparison",
    ),
) -> SearchResponse:
    """Find artifacts similar to a given artifact - "more like this" exploration.
    
    ## When to Use Similarity Search
    
    **Best for:**
    - "Show me more like this" exploration from a known artifact
    - Finding related content when you have a good starting point
    - Building recommendation features ("you might also find relevant...")
    - Discovering connections in your knowledge graph
    
    **Examples:**
    - User is reading a decision, wants to see similar decisions
    - Finding related analyses after reviewing a document
    - Exploring thematically connected content
    
    ## How It Works
    
    1. Looks up the embedding of the specified artifact
    2. Runs semantic search using that embedding as the query
    3. Returns similar artifacts, excluding the source artifact itself
    
    **Note:** The artifact must have an embedding. If it doesn't, returns empty results.
    
    ## Compared to Other Search Types
    
    | Approach | Input | Best For |
    |----------|-------|----------|
    | Fulltext | Text query | Known keywords |
    | Semantic | Embedding vector | Conceptual search |
    | Hybrid | Text + embedding | Production RAG |
    | **Similar** | Artifact UUID | "More like this" |
    
    ## Filtering by Type
    
    Use `artifact_types` to constrain what kind of similar artifacts you want:
    
    **Scenario:** "Show me decisions similar to this decision"
    ```
    GET /search/similar/{decision_uuid}?artifact_types=decision
    ```
    
    **Scenario:** "Find summaries and notes related to this document"
    ```
    GET /search/similar/{doc_uuid}?artifact_types=summary&artifact_types=note
    ```
    """
    return await search_service.similar_artifacts(
        x_tenant_id, artifact_id, limit, artifact_types, model
    )