"""Embeddings API routes."""

from fastapi import APIRouter, Header, HTTPException, status

from mimir.schemas.embedding import (
    EmbeddingBatchCreate,
    EmbeddingBatchResponse,
    EmbeddingCreate,
    EmbeddingListResponse,
    EmbeddingResponse,
)
from mimir.services import embedding_service

router = APIRouter(prefix="/embeddings", tags=["embeddings"])


@router.post("", response_model=EmbeddingResponse, status_code=status.HTTP_201_CREATED)
async def create_embedding(
    data: EmbeddingCreate,
    x_tenant_id: int = Header(..., description="Tenant ID"),
) -> EmbeddingResponse:
    """Create an embedding for an artifact.

    Generates a vector embedding using the specified model and stores it.
    Requires OPENAI_API_KEY environment variable for OpenAI models.
    """
    try:
        return await embedding_service.create_embedding(x_tenant_id, data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post(
    "/batch", response_model=EmbeddingBatchResponse, status_code=status.HTTP_201_CREATED
)
async def create_embeddings_batch(
    data: EmbeddingBatchCreate,
    x_tenant_id: int = Header(..., description="Tenant ID"),
) -> EmbeddingBatchResponse:
    """Create embeddings for multiple artifacts in batch.

    Processes multiple artifacts efficiently using batched API calls.
    Returns counts of successful and failed embeddings.
    """
    return await embedding_service.create_embeddings_batch(x_tenant_id, data)


@router.get("/{embedding_id}", response_model=EmbeddingResponse)
async def get_embedding(
    embedding_id: int,
    x_tenant_id: int = Header(..., description="Tenant ID"),
) -> EmbeddingResponse:
    """Get an embedding by ID."""
    embedding = await embedding_service.get_embedding(embedding_id, x_tenant_id)
    if not embedding:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Embedding not found"
        )
    return embedding


@router.get("", response_model=EmbeddingListResponse)
async def list_embeddings(
    x_tenant_id: int = Header(..., description="Tenant ID"),
    page: int = 1,
    page_size: int = 20,
    artifact_id: int | None = None,
    model: str | None = None,
) -> EmbeddingListResponse:
    """List embeddings with pagination and optional filtering.

    Filters:
    - artifact_id: Filter by specific artifact
    - model: Filter by embedding model
    """
    return await embedding_service.list_embeddings(
        x_tenant_id,
        page=page,
        page_size=page_size,
        artifact_id=artifact_id,
        model=model,
    )


@router.delete("/{embedding_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_embedding(
    embedding_id: int,
    x_tenant_id: int = Header(..., description="Tenant ID"),
) -> None:
    """Delete an embedding by ID."""
    deleted = await embedding_service.delete_embedding(embedding_id, x_tenant_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Embedding not found"
        )


@router.delete("/artifact/{artifact_id}", status_code=status.HTTP_200_OK)
async def delete_embeddings_by_artifact(
    artifact_id: int,
    x_tenant_id: int = Header(..., description="Tenant ID"),
) -> dict:
    """Delete all embeddings for an artifact.

    Returns the count of deleted embeddings.
    """
    count = await embedding_service.delete_embeddings_by_artifact(
        artifact_id, x_tenant_id
    )
    return {"deleted": count}
