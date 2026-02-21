"""Embedding API endpoints (V2.1 multi-table architecture).

V2.1 Changes:
- Uses embedding_type FK instead of free-form model string
- Vectors stored in separate mimir_vectors.vec_{type} tables
- Requires embedding_type for similarity search
- No DELETE endpoint (append-only)
"""

from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Query

from mimir.schemas.embedding import (
    EmbeddingCreate,
    EmbeddingListResponse,
    EmbeddingResponse,
    EmbeddingWithVectorResponse,
    SimilaritySearchRequest,
    SimilaritySearchResponse,
)
from mimir.services import embedding_service

router = APIRouter(prefix="/embeddings", tags=["embeddings"])


@router.post("", response_model=EmbeddingResponse, status_code=201)
async def create_embedding(
    data: EmbeddingCreate,
    x_tenant_id: int = Header(..., alias="X-Tenant-ID"),
) -> EmbeddingResponse:
    """Create a new embedding for an artifact.

    Requires the embedding_type to be registered first via POST /embedding-types.
    The vector dimensions must match the embedding_type definition.
    """
    try:
        return await embedding_service.create_embedding(x_tenant_id, data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("", response_model=EmbeddingListResponse)
async def list_embeddings(
    x_tenant_id: int = Header(..., alias="X-Tenant-ID"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    artifact_id: UUID | None = Query(None, description="Filter by artifact UUID"),
    embedding_type: str | None = Query(None, description="Filter by embedding type"),
) -> EmbeddingListResponse:
    """List embeddings with optional filtering."""
    return await embedding_service.list_embeddings(
        x_tenant_id, limit, offset, artifact_id, embedding_type
    )


@router.get("/{embedding_id}", response_model=EmbeddingResponse)
async def get_embedding(
    embedding_id: UUID,
    x_tenant_id: int = Header(..., alias="X-Tenant-ID"),
    include_vector: bool = Query(False, description="Include embedding vector"),
) -> EmbeddingResponse | EmbeddingWithVectorResponse:
    """Get embedding by UUID."""
    result = await embedding_service.get_embedding(
        embedding_id, x_tenant_id, include_vector
    )
    if not result:
        raise HTTPException(status_code=404, detail="Embedding not found")
    return result


@router.get("/artifact/{artifact_id}", response_model=list[EmbeddingResponse])
async def get_artifact_embeddings(
    artifact_id: UUID,
    x_tenant_id: int = Header(..., alias="X-Tenant-ID"),
    embedding_type: str | None = Query(None, description="Filter by embedding type"),
) -> list[EmbeddingResponse]:
    """Get all embeddings for an artifact."""
    return await embedding_service.get_artifact_embeddings(
        x_tenant_id, artifact_id, embedding_type
    )


@router.post("/similar", response_model=SimilaritySearchResponse)
async def find_similar(
    request: SimilaritySearchRequest,
    x_tenant_id: int = Header(..., alias="X-Tenant-ID"),
) -> SimilaritySearchResponse:
    """Find similar embeddings by vector.

    Requires embedding_type to know which vector table to search.
    You cannot search across different embedding types (different dimensions).
    """
    try:
        return await embedding_service.find_similar(
            tenant_id=x_tenant_id,
            query_vector=request.query_vector,
            embedding_type=request.embedding_type,
            limit=request.limit,
            artifact_types=request.artifact_types,
            similarity_threshold=request.similarity_threshold,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


# NOTE: DELETE endpoints removed - embeddings are append-only
