"""Embedding service - database operations for embeddings (V2 append-only).

V2 Changes:
- UUID primary keys (server-generated)
- UUID artifact references (not entity_type/entity_id INT)
- Simplified - no chunk_index/start/end (chunks are artifacts)
- Append-only: no delete operations
"""

from uuid import UUID, uuid4

from psycopg.types.json import Json

from mimir.database import get_connection
from mimir.schemas.embedding import (
    EmbeddingCreate,
    EmbeddingListResponse,
    EmbeddingResponse,
    EmbeddingWithVectorResponse,
)
from mimir.services import provenance_service

SCHEMA_NAME = "mimirdata"


async def create_embedding(tenant_id: int, data: EmbeddingCreate) -> EmbeddingResponse:
    """Create a new embedding."""
    embedding_id = uuid4()
    dimensions = len(data.embedding)
    vector_str = "[" + ",".join(str(v) for v in data.embedding) + "]"

    async with get_connection() as conn:
        result = await conn.execute(
            f"""
            INSERT INTO {SCHEMA_NAME}.embedding
                (id, tenant_id, artifact_id, model, dimensions, embedding, metadata)
            VALUES (%s, %s, %s, %s, %s, %s::vector, %s)
            RETURNING id, tenant_id, artifact_id, model, dimensions, metadata, created_at
            """,
            (
                str(embedding_id),
                tenant_id,
                str(data.artifact_id),
                data.model,
                dimensions,
                vector_str,
                Json(data.metadata) if data.metadata else None,
            ),
        )
        row = await result.fetchone()
        await conn.commit()

    embedding = _row_to_embedding_response(row)

    # Log provenance event
    await provenance_service.log_action(
        tenant_id=tenant_id,
        entity_type="embedding",
        entity_id=embedding.id,
        action="create",
        actor_type="api_client",
        metadata={"model": embedding.model, "artifact_id": str(embedding.artifact_id)},
    )

    return embedding


async def get_embedding(
    embedding_id: UUID, tenant_id: int, include_vector: bool = False
) -> EmbeddingResponse | EmbeddingWithVectorResponse | None:
    """Get embedding by UUID."""
    async with get_connection() as conn:
        if include_vector:
            result = await conn.execute(
                f"""
                SELECT id, tenant_id, artifact_id, model, dimensions, metadata, 
                       created_at, embedding::text
                FROM {SCHEMA_NAME}.embedding
                WHERE id = %s AND tenant_id = %s
                """,
                (str(embedding_id), tenant_id),
            )
        else:
            result = await conn.execute(
                f"""
                SELECT id, tenant_id, artifact_id, model, dimensions, metadata, created_at
                FROM {SCHEMA_NAME}.embedding
                WHERE id = %s AND tenant_id = %s
                """,
                (str(embedding_id), tenant_id),
            )
        row = await result.fetchone()

    if not row:
        return None

    if include_vector:
        return _row_to_embedding_with_vector(row)
    return _row_to_embedding_response(row)


async def list_embeddings(
    tenant_id: int,
    limit: int = 50,
    offset: int = 0,
    artifact_id: UUID | None = None,
    model: str | None = None,
) -> EmbeddingListResponse:
    """List embeddings with optional filtering."""
    async with get_connection() as conn:
        where_clause = "WHERE tenant_id = %s"
        params: list = [tenant_id]

        if artifact_id:
            where_clause += " AND artifact_id = %s"
            params.append(str(artifact_id))
        if model:
            where_clause += " AND model = %s"
            params.append(model)

        # Get count
        count_result = await conn.execute(
            f"SELECT COUNT(*) FROM {SCHEMA_NAME}.embedding {where_clause}",
            params,
        )
        total = (await count_result.fetchone())[0]

        # Get embeddings
        result = await conn.execute(
            f"""
            SELECT id, tenant_id, artifact_id, model, dimensions, metadata, created_at
            FROM {SCHEMA_NAME}.embedding
            {where_clause}
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
            """,
            params + [limit, offset],
        )
        rows = await result.fetchall()

    items = [_row_to_embedding_response(row) for row in rows]

    return EmbeddingListResponse(items=items, total=total, limit=limit, offset=offset)


async def get_artifact_embeddings(
    tenant_id: int,
    artifact_id: UUID,
    model: str | None = None,
) -> list[EmbeddingResponse]:
    """Get all embeddings for an artifact."""
    async with get_connection() as conn:
        where_clause = "WHERE tenant_id = %s AND artifact_id = %s"
        params: list = [tenant_id, str(artifact_id)]

        if model:
            where_clause += " AND model = %s"
            params.append(model)

        result = await conn.execute(
            f"""
            SELECT id, tenant_id, artifact_id, model, dimensions, metadata, created_at
            FROM {SCHEMA_NAME}.embedding
            {where_clause}
            ORDER BY created_at DESC
            """,
            params,
        )
        rows = await result.fetchall()

    return [_row_to_embedding_response(row) for row in rows]


async def find_similar(
    tenant_id: int,
    query_vector: list[float],
    limit: int = 20,
    model: str | None = None,
    artifact_types: list[str] | None = None,
    similarity_threshold: float = 0.0,
) -> list[tuple[EmbeddingResponse, float]]:
    """Find embeddings similar to query vector using cosine distance."""
    vector_str = "[" + ",".join(str(v) for v in query_vector) + "]"

    async with get_connection() as conn:
        where_clause = "WHERE e.tenant_id = %s"
        params: list = [tenant_id]

        if model:
            where_clause += " AND e.model = %s"
            params.append(model)

        # Join with artifact to filter by type
        join_clause = ""
        if artifact_types:
            join_clause = f"JOIN {SCHEMA_NAME}.artifact a ON e.artifact_id = a.id"
            where_clause += " AND a.artifact_type = ANY(%s)"
            params.append(artifact_types)

        # Use cosine distance (<=> operator)
        result = await conn.execute(
            f"""
            SELECT e.id, e.tenant_id, e.artifact_id, e.model, e.dimensions, 
                   e.metadata, e.created_at,
                   1 - (e.embedding <=> %s::vector) as similarity
            FROM {SCHEMA_NAME}.embedding e
            {join_clause}
            {where_clause}
            ORDER BY e.embedding <=> %s::vector
            LIMIT %s
            """,
            params + [vector_str, vector_str, limit],
        )
        rows = await result.fetchall()

    results = []
    for row in rows:
        similarity = row[7]
        if similarity >= similarity_threshold:
            embedding = _row_to_embedding_response(row[:7])
            results.append((embedding, similarity))

    return results


async def check_embedding_exists(
    tenant_id: int,
    artifact_id: UUID,
    model: str,
) -> bool:
    """Check if embedding already exists for artifact/model combination."""
    async with get_connection() as conn:
        result = await conn.execute(
            f"""
            SELECT 1 FROM {SCHEMA_NAME}.embedding 
            WHERE tenant_id = %s AND artifact_id = %s AND model = %s
            """,
            (tenant_id, str(artifact_id), model),
        )
        row = await result.fetchone()

    return row is not None


def _row_to_embedding_response(row: tuple) -> EmbeddingResponse:
    """Convert database row to EmbeddingResponse."""
    return EmbeddingResponse(
        id=UUID(row[0]) if isinstance(row[0], str) else row[0],
        tenant_id=row[1],
        artifact_id=UUID(row[2]) if isinstance(row[2], str) else row[2],
        model=row[3],
        dimensions=row[4],
        metadata=row[5],
        created_at=row[6],
    )


def _row_to_embedding_with_vector(row: tuple) -> EmbeddingWithVectorResponse:
    """Convert database row with vector to EmbeddingWithVectorResponse."""
    # Parse vector string: "[1.0,2.0,3.0]" -> [1.0, 2.0, 3.0]
    vector_str = row[7]
    vector = [float(v) for v in vector_str.strip("[]").split(",")]

    return EmbeddingWithVectorResponse(
        id=UUID(row[0]) if isinstance(row[0], str) else row[0],
        tenant_id=row[1],
        artifact_id=UUID(row[2]) if isinstance(row[2], str) else row[2],
        model=row[3],
        dimensions=row[4],
        metadata=row[5],
        created_at=row[6],
        embedding=vector,
    )


# NOTE: delete_embedding and delete_entity_embeddings removed - embeddings are append-only
