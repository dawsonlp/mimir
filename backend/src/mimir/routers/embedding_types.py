"""Embedding Type API endpoints.

Manages embedding model types and creates corresponding vector tables.
"""

from fastapi import APIRouter, HTTPException, Query

from mimir.schemas.embedding_type import (
    EmbeddingTypeCreate,
    EmbeddingTypeListResponse,
    EmbeddingTypeResponse,
)
from mimir.services import embedding_type_service

router = APIRouter(prefix="/embedding-types", tags=["embedding-types"])


@router.post("", response_model=EmbeddingTypeResponse, status_code=201)
async def create_embedding_type(
    data: EmbeddingTypeCreate,
) -> EmbeddingTypeResponse:
    """Create a new embedding type and its vector table.

    This operation:
    1. Creates an embedding_type record
    2. Creates a vector table in mimir_vectors schema
    3. Creates an HNSW index for similarity search
    """
    try:
        return await embedding_type_service.create_embedding_type(data)
    except Exception as e:
        if "duplicate key" in str(e).lower():
            raise HTTPException(
                status_code=409, detail=f"Embedding type '{data.code}' already exists"
            ) from e
        raise


@router.get("", response_model=EmbeddingTypeListResponse)
async def list_embedding_types(
    active_only: bool = Query(True, description="Only return active types"),
    provider: str | None = Query(None, description="Filter by provider"),
) -> EmbeddingTypeListResponse:
    """List all embedding types."""
    return await embedding_type_service.list_embedding_types(active_only, provider)


@router.get("/{code}", response_model=EmbeddingTypeResponse)
async def get_embedding_type(
    code: str,
) -> EmbeddingTypeResponse:
    """Get embedding type by code."""
    result = await embedding_type_service.get_embedding_type(code)
    if not result:
        raise HTTPException(status_code=404, detail="Embedding type not found")
    return result


@router.delete("/{code}", status_code=204)
async def deactivate_embedding_type(
    code: str,
) -> None:
    """Soft delete (deactivate) an embedding type.

    Note: Does not drop the vector table - embeddings remain accessible.
    """
    success = await embedding_type_service.deactivate_embedding_type(code)
    if not success:
        raise HTTPException(status_code=404, detail="Embedding type not found")
