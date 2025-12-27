"""Search and Embedding API endpoints."""

from fastapi import APIRouter, Header, HTTPException, Query

from mimir.schemas.embedding import (
    EmbeddingBatchCreate,
    EmbeddingBatchResponse,
    EmbeddingCreate,
    EmbeddingListResponse,
    EmbeddingResponse,
)
from mimir.schemas.search import (
    FulltextSearchRequest,
    SearchRequest,
    SearchResponse,
    SemanticSearchRequest,
    SimilarArtifactsRequest,
)
from mimir.services import embedding_service, search_service

router = APIRouter(tags=["search"])


# ============================================================================
# Search Endpoints
# ============================================================================


@router.post("/search", response_model=SearchResponse)
async def search(
    request: SearchRequest,
    x_tenant_id: int = Header(..., description="Tenant ID"),
) -> SearchResponse:
    """Unified search endpoint supporting semantic, full-text, and hybrid search.

    - **semantic**: Uses vector similarity search via pgvector
    - **fulltext**: Uses PostgreSQL full-text search with tsvector/tsquery
    - **hybrid**: Combines both using Reciprocal Rank Fusion (RRF)
    """
    try:
        return await search_service.search(x_tenant_id, request)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None


@router.post("/search/semantic", response_model=SearchResponse)
async def semantic_search(
    request: SemanticSearchRequest,
    x_tenant_id: int = Header(..., description="Tenant ID"),
) -> SearchResponse:
    """Semantic search using vector similarity.

    Requires embeddings to be generated for artifacts first.
    Uses cosine similarity with HNSW index for approximate nearest neighbor search.
    """
    try:
        return await search_service.semantic_search(x_tenant_id, request)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None


@router.post("/search/fulltext", response_model=SearchResponse)
async def fulltext_search(
    request: FulltextSearchRequest,
    x_tenant_id: int = Header(..., description="Tenant ID"),
) -> SearchResponse:
    """Full-text search using PostgreSQL tsvector/tsquery.

    Searches artifact titles and content using GIN indexes.
    Results are ranked by relevance.
    """
    return await search_service.fulltext_search(x_tenant_id, request)


@router.post("/search/similar", response_model=SearchResponse)
async def find_similar(
    request: SimilarArtifactsRequest,
    x_tenant_id: int = Header(..., description="Tenant ID"),
) -> SearchResponse:
    """Find artifacts similar to a given artifact.

    Uses the existing embedding for the source artifact to find similar ones.
    Requires the source artifact to have an embedding generated.
    """
    return await search_service.find_similar_artifacts(x_tenant_id, request)


# ============================================================================
# Embedding Endpoints
# ============================================================================


@router.post("/embeddings", response_model=EmbeddingResponse, status_code=201)
async def create_embedding(
    data: EmbeddingCreate,
    x_tenant_id: int = Header(..., description="Tenant ID"),
) -> EmbeddingResponse:
    """Create an embedding for an artifact.

    Generates a vector embedding using the specified model and stores it
    for future semantic search operations.
    """
    try:
        return await embedding_service.create_embedding(x_tenant_id, data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None


@router.post("/embeddings/batch", response_model=EmbeddingBatchResponse, status_code=201)
async def create_embeddings_batch(
    data: EmbeddingBatchCreate,
    x_tenant_id: int = Header(..., description="Tenant ID"),
) -> EmbeddingBatchResponse:
    """Create embeddings for multiple artifacts in batch.

    More efficient than creating embeddings one at a time.
    Returns counts of successful and failed embeddings.
    """
    try:
        return await embedding_service.create_embeddings_batch(x_tenant_id, data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None


@router.get("/embeddings", response_model=EmbeddingListResponse)
async def list_embeddings(
    x_tenant_id: int = Header(..., description="Tenant ID"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    artifact_id: int | None = Query(None, description="Filter by artifact ID"),
    model: str | None = Query(None, description="Filter by embedding model"),
) -> EmbeddingListResponse:
    """List embeddings for the tenant with pagination and filtering."""
    return await embedding_service.list_embeddings(
        x_tenant_id, page, page_size, artifact_id, model
    )


@router.get("/embeddings/{embedding_id}", response_model=EmbeddingResponse)
async def get_embedding(
    embedding_id: int,
    x_tenant_id: int = Header(..., description="Tenant ID"),
) -> EmbeddingResponse:
    """Get embedding by ID."""
    result = await embedding_service.get_embedding(embedding_id, x_tenant_id)
    if not result:
        raise HTTPException(status_code=404, detail="Embedding not found")
    return result


@router.delete("/embeddings/{embedding_id}", status_code=204)
async def delete_embedding(
    embedding_id: int,
    x_tenant_id: int = Header(..., description="Tenant ID"),
) -> None:
    """Delete an embedding."""
    deleted = await embedding_service.delete_embedding(embedding_id, x_tenant_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Embedding not found")


@router.delete("/embeddings/artifact/{artifact_id}", status_code=200)
async def delete_embeddings_by_artifact(
    artifact_id: int,
    x_tenant_id: int = Header(..., description="Tenant ID"),
) -> dict:
    """Delete all embeddings for an artifact.

    Returns the count of deleted embeddings.
    """
    count = await embedding_service.delete_embeddings_by_artifact(artifact_id, x_tenant_id)
    return {"deleted": count}
