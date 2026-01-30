"""Embedding API endpoints (V2 append-only).

V2 Changes:
- UUID path parameters (not INT)
- UUID artifact references (not entity_type/entity_id INT)
- No DELETE endpoint (append-only)
"""

from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Query

from mimir.schemas.embedding import (
    EmbeddingCreate,
    EmbeddingListResponse,
    EmbeddingResponse,
    EmbeddingWithVectorResponse,
)
from mimir.services import embedding_service

router = APIRouter(prefix="/embeddings", tags=["embeddings"])


@router.post("", response_model=EmbeddingResponse, status_code=201)
async def create_embedding(
    data: EmbeddingCreate,
    x_tenant_id: int = Header(..., alias="X-Tenant-ID"),
) -> EmbeddingResponse:
    """Create a new embedding for an artifact."""
    return await embedding_service.create_embedding(x_tenant_id, data)


@router.get("", response_model=EmbeddingListResponse)
async def list_embeddings(
    x_tenant_id: int = Header(..., alias="X-Tenant-ID"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    artifact_id: UUID | None = Query(None),
    model: str | None = Query(None),
) -> EmbeddingListResponse:
    """List embeddings with optional filtering."""
    return await embedding_service.list_embeddings(
        x_tenant_id, limit, offset, artifact_id, model
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
    model: str | None = Query(None),
) -> list[EmbeddingResponse]:
    """Get all embeddings for an artifact."""
    return await embedding_service.get_artifact_embeddings(
        x_tenant_id, artifact_id, model
    )


@router.post("/similar")
async def find_similar(
    query_vector: list[float],
    x_tenant_id: int = Header(..., alias="X-Tenant-ID"),
    limit: int = Query(20, ge=1, le=100),
    model: str | None = Query(None),
    artifact_types: list[str] | None = Query(None),
    similarity_threshold: float = Query(0.0, ge=0.0, le=1.0),
) -> list[dict]:
    """Find similar embeddings by vector."""
    results = await embedding_service.find_similar(
        x_tenant_id, query_vector, limit, model, artifact_types, similarity_threshold
    )
    return [
        {"embedding": emb.model_dump(), "similarity": score}
        for emb, score in results
    ]


# NOTE: DELETE endpoints removed - embeddings are append-only
