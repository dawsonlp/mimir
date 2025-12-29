"""Search API endpoints (V2)."""

from fastapi import APIRouter, Header, Query

from mimir.schemas.search import SearchResponse
from mimir.services import search_service

router = APIRouter(prefix="/search", tags=["search"])


@router.get("/fulltext", response_model=SearchResponse)
async def fulltext_search(
    query: str,
    x_tenant_id: int = Header(..., alias="X-Tenant-ID"),
    artifact_types: list[str] | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> SearchResponse:
    """Full-text search using PostgreSQL FTS."""
    return await search_service.fulltext_search(
        x_tenant_id, query, artifact_types, limit, offset
    )


@router.post("/semantic", response_model=SearchResponse)
async def semantic_search(
    query_vector: list[float],
    x_tenant_id: int = Header(..., alias="X-Tenant-ID"),
    artifact_types: list[str] | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    similarity_threshold: float = Query(0.0, ge=0.0, le=1.0),
    model: str | None = Query(None),
) -> SearchResponse:
    """Semantic search using vector similarity."""
    return await search_service.semantic_search(
        x_tenant_id,
        query_vector,
        artifact_types,
        limit,
        similarity_threshold,
        model,
    )


@router.post("/hybrid", response_model=SearchResponse)
async def hybrid_search(
    query: str,
    query_vector: list[float],
    x_tenant_id: int = Header(..., alias="X-Tenant-ID"),
    artifact_types: list[str] | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    rrf_k: int = Query(60, ge=1, description="RRF ranking constant"),
    semantic_weight: float = Query(0.5, ge=0.0, le=1.0),
    model: str | None = Query(None),
) -> SearchResponse:
    """Hybrid search using Reciprocal Rank Fusion (RRF)."""
    return await search_service.hybrid_search(
        x_tenant_id,
        query,
        query_vector,
        artifact_types,
        limit,
        rrf_k,
        semantic_weight,
        model,
    )


@router.get("/similar/{artifact_id}", response_model=SearchResponse)
async def similar_artifacts(
    artifact_id: int,
    x_tenant_id: int = Header(..., alias="X-Tenant-ID"),
    limit: int = Query(10, ge=1, le=50),
    artifact_types: list[str] | None = Query(None),
    model: str | None = Query(None),
) -> SearchResponse:
    """Find artifacts similar to a given artifact."""
    return await search_service.similar_artifacts(
        x_tenant_id, artifact_id, limit, artifact_types, model
    )
