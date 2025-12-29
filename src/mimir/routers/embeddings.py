"""Embedding API endpoints (V2)."""

from fastapi import APIRouter, Header, HTTPException, Query

from mimir.schemas.embedding import (
    EmbeddingCreate,
    EmbeddingListResponse,
    EmbeddingResponse,
    EmbeddingWithVectorResponse,
)
from mimir.schemas.relation import EntityType
from mimir.services import embedding_service

router = APIRouter(prefix="/embeddings", tags=["embeddings"])


@router.post("", response_model=EmbeddingResponse, status_code=201)
async def create_embedding(
    data: EmbeddingCreate,
    x_tenant_id: int = Header(..., alias="X-Tenant-ID"),
) -> EmbeddingResponse:
    """Create a new embedding."""
    return await embedding_service.create_embedding(x_tenant_id, data)


@router.get("", response_model=EmbeddingListResponse)
async def list_embeddings(
    x_tenant_id: int = Header(..., alias="X-Tenant-ID"),
    entity_type: EntityType | None = Query(None),
    entity_id: int | None = Query(None),
    model: str | None = Query(None),
) -> EmbeddingListResponse:
    """List embeddings with optional filtering."""
    return await embedding_service.list_embeddings(
        x_tenant_id, entity_type, entity_id, model
    )


@router.get("/{embedding_id}", response_model=EmbeddingResponse)
async def get_embedding(
    embedding_id: int,
    x_tenant_id: int = Header(..., alias="X-Tenant-ID"),
    include_vector: bool = Query(False, description="Include embedding vector"),
) -> EmbeddingResponse | EmbeddingWithVectorResponse:
    """Get embedding by ID."""
    result = await embedding_service.get_embedding(
        embedding_id, x_tenant_id, include_vector
    )
    if not result:
        raise HTTPException(status_code=404, detail="Embedding not found")
    return result


@router.delete("/{embedding_id}", status_code=204)
async def delete_embedding(
    embedding_id: int,
    x_tenant_id: int = Header(..., alias="X-Tenant-ID"),
) -> None:
    """Delete an embedding."""
    deleted = await embedding_service.delete_embedding(embedding_id, x_tenant_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Embedding not found")


@router.delete("/entity/{entity_type}/{entity_id}")
async def delete_entity_embeddings(
    entity_type: EntityType,
    entity_id: int,
    x_tenant_id: int = Header(..., alias="X-Tenant-ID"),
    model: str | None = Query(None, description="Delete only for specific model"),
) -> dict:
    """Delete all embeddings for an entity."""
    count = await embedding_service.delete_entity_embeddings(
        x_tenant_id, entity_type, entity_id, model
    )
    return {"deleted": count}


@router.post("/similar")
async def find_similar(
    query_vector: list[float],
    x_tenant_id: int = Header(..., alias="X-Tenant-ID"),
    limit: int = Query(20, ge=1, le=100),
    entity_type: EntityType | None = Query(None),
    model: str | None = Query(None),
    similarity_threshold: float = Query(0.0, ge=0.0, le=1.0),
) -> list[dict]:
    """Find similar embeddings by vector."""
    results = await embedding_service.find_similar(
        x_tenant_id, query_vector, limit, entity_type, model, similarity_threshold
    )
    return [
        {"embedding": emb.model_dump(), "similarity": score}
        for emb, score in results
    ]
