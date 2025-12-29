"""Embedding service - database operations for embeddings (V2)."""

from mimir.database import get_connection
from mimir.schemas.embedding import (
    EmbeddingCreate,
    EmbeddingListResponse,
    EmbeddingResponse,
    EmbeddingWithVectorResponse,
)
from mimir.schemas.relation import EntityType

SCHEMA_NAME = "mimirdata"


async def create_embedding(tenant_id: int, data: EmbeddingCreate) -> EmbeddingResponse:
    """Create a new embedding."""
    dimensions = len(data.embedding)
    vector_str = "[" + ",".join(str(v) for v in data.embedding) + "]"

    async with get_connection() as conn:
        result = await conn.execute(
            f"""
            INSERT INTO {SCHEMA_NAME}.embedding
                (tenant_id, entity_type, entity_id, model, embedding, dimensions,
                 chunk_index, chunk_start, chunk_end)
            VALUES (%s, %s, %s, %s, %s::vector, %s, %s, %s, %s)
            RETURNING id, tenant_id, entity_type, entity_id, model, dimensions,
                      chunk_index, chunk_start, chunk_end, created_at
            """,
            (
                tenant_id,
                data.entity_type.value,
                data.entity_id,
                data.model,
                vector_str,
                dimensions,
                data.chunk_index,
                data.chunk_start,
                data.chunk_end,
            ),
        )
        row = await result.fetchone()
        await conn.commit()

    return _row_to_embedding_response(row)


async def get_embedding(
    embedding_id: int, tenant_id: int, include_vector: bool = False
) -> EmbeddingResponse | EmbeddingWithVectorResponse | None:
    """Get embedding by ID."""
    async with get_connection() as conn:
        if include_vector:
            result = await conn.execute(
                f"""
                SELECT id, tenant_id, entity_type, entity_id, model, dimensions,
                       chunk_index, chunk_start, chunk_end, created_at, embedding::text
                FROM {SCHEMA_NAME}.embedding
                WHERE id = %s AND tenant_id = %s
                """,
                (embedding_id, tenant_id),
            )
        else:
            result = await conn.execute(
                f"""
                SELECT id, tenant_id, entity_type, entity_id, model, dimensions,
                       chunk_index, chunk_start, chunk_end, created_at
                FROM {SCHEMA_NAME}.embedding
                WHERE id = %s AND tenant_id = %s
                """,
                (embedding_id, tenant_id),
            )
        row = await result.fetchone()

    if not row:
        return None

    if include_vector:
        return _row_to_embedding_with_vector(row)
    return _row_to_embedding_response(row)


async def list_embeddings(
    tenant_id: int,
    entity_type: EntityType | None = None,
    entity_id: int | None = None,
    model: str | None = None,
) -> EmbeddingListResponse:
    """List embeddings with optional filtering."""
    async with get_connection() as conn:
        where_clause = "WHERE tenant_id = %s"
        params: list = [tenant_id]

        if entity_type:
            where_clause += " AND entity_type = %s"
            params.append(entity_type.value)
        if entity_id is not None:
            where_clause += " AND entity_id = %s"
            params.append(entity_id)
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
            SELECT id, tenant_id, entity_type, entity_id, model, dimensions,
                   chunk_index, chunk_start, chunk_end, created_at
            FROM {SCHEMA_NAME}.embedding
            {where_clause}
            ORDER BY created_at DESC
            """,
            params,
        )
        rows = await result.fetchall()

    items = [_row_to_embedding_response(row) for row in rows]

    return EmbeddingListResponse(items=items, total=total)


async def delete_embedding(embedding_id: int, tenant_id: int) -> bool:
    """Delete an embedding."""
    async with get_connection() as conn:
        result = await conn.execute(
            f"""
            DELETE FROM {SCHEMA_NAME}.embedding
            WHERE id = %s AND tenant_id = %s
            RETURNING id
            """,
            (embedding_id, tenant_id),
        )
        row = await result.fetchone()
        await conn.commit()

    return row is not None


async def delete_entity_embeddings(
    tenant_id: int,
    entity_type: EntityType,
    entity_id: int,
    model: str | None = None,
) -> int:
    """Delete all embeddings for an entity."""
    async with get_connection() as conn:
        where_clause = "WHERE tenant_id = %s AND entity_type = %s AND entity_id = %s"
        params: list = [tenant_id, entity_type.value, entity_id]

        if model:
            where_clause += " AND model = %s"
            params.append(model)

        result = await conn.execute(
            f"""
            DELETE FROM {SCHEMA_NAME}.embedding
            {where_clause}
            RETURNING id
            """,
            params,
        )
        rows = await result.fetchall()
        await conn.commit()

    return len(rows)


async def find_similar(
    tenant_id: int,
    query_vector: list[float],
    limit: int = 20,
    entity_type: EntityType | None = None,
    model: str | None = None,
    similarity_threshold: float = 0.0,
) -> list[tuple[EmbeddingResponse, float]]:
    """Find embeddings similar to query vector using cosine distance."""
    vector_str = "[" + ",".join(str(v) for v in query_vector) + "]"

    async with get_connection() as conn:
        where_clause = "WHERE tenant_id = %s"
        params: list = [tenant_id]

        if entity_type:
            where_clause += " AND entity_type = %s"
            params.append(entity_type.value)
        if model:
            where_clause += " AND model = %s"
            params.append(model)

        # Use cosine distance (<=> operator)
        result = await conn.execute(
            f"""
            SELECT id, tenant_id, entity_type, entity_id, model, dimensions,
                   chunk_index, chunk_start, chunk_end, created_at,
                   1 - (embedding <=> %s::vector) as similarity
            FROM {SCHEMA_NAME}.embedding
            {where_clause}
            ORDER BY embedding <=> %s::vector
            LIMIT %s
            """,
            params + [vector_str, vector_str, limit],
        )
        rows = await result.fetchall()

    results = []
    for row in rows:
        similarity = row[10]
        if similarity >= similarity_threshold:
            embedding = _row_to_embedding_response(row[:10])
            results.append((embedding, similarity))

    return results


async def check_embedding_exists(
    tenant_id: int,
    entity_type: EntityType,
    entity_id: int,
    model: str,
    chunk_index: int | None = None,
) -> bool:
    """Check if embedding already exists for entity/model combination."""
    async with get_connection() as conn:
        where_clause = """
            WHERE tenant_id = %s AND entity_type = %s AND entity_id = %s AND model = %s
        """
        params: list = [tenant_id, entity_type.value, entity_id, model]

        if chunk_index is not None:
            where_clause += " AND chunk_index = %s"
            params.append(chunk_index)
        else:
            where_clause += " AND chunk_index IS NULL"

        result = await conn.execute(
            f"SELECT 1 FROM {SCHEMA_NAME}.embedding {where_clause}",
            params,
        )
        row = await result.fetchone()

    return row is not None


def _row_to_embedding_response(row: tuple) -> EmbeddingResponse:
    """Convert database row to EmbeddingResponse."""
    return EmbeddingResponse(
        id=row[0],
        tenant_id=row[1],
        entity_type=EntityType(row[2]),
        entity_id=row[3],
        model=row[4],
        dimensions=row[5],
        chunk_index=row[6],
        chunk_start=row[7],
        chunk_end=row[8],
        created_at=row[9],
    )


def _row_to_embedding_with_vector(row: tuple) -> EmbeddingWithVectorResponse:
    """Convert database row with vector to EmbeddingWithVectorResponse."""
    # Parse vector string: "[1.0,2.0,3.0]" -> [1.0, 2.0, 3.0]
    vector_str = row[10]
    vector = [float(v) for v in vector_str.strip("[]").split(",")]

    return EmbeddingWithVectorResponse(
        id=row[0],
        tenant_id=row[1],
        entity_type=EntityType(row[2]),
        entity_id=row[3],
        model=row[4],
        dimensions=row[5],
        chunk_index=row[6],
        chunk_start=row[7],
        chunk_end=row[8],
        created_at=row[9],
        embedding=vector,
    )
