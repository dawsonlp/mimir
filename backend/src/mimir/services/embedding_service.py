"""Embedding service - database operations for embeddings (multi-table architecture).

Features:
- Uses embedding_type FK instead of free-form model string
- Vectors stored in mimir_vectors.vec_{type} child tables
- Validates dimensions against embedding_type definition
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
    SimilarityResult,
    SimilaritySearchResponse,
)
from mimir.services import provenance_service

SCHEMA_NAME = "mimirdata"
VECTOR_SCHEMA = "mimir_vectors"


async def _get_embedding_type_info(embedding_type: str) -> tuple[int, str] | None:
    """Get embedding type dimensions and vector table name."""
    async with get_connection() as conn:
        result = await conn.execute(
            f"""
            SELECT dimensions, vector_table_name
            FROM {SCHEMA_NAME}.embedding_type
            WHERE code = %s AND is_active = true
            """,
            (embedding_type,),
        )
        row = await result.fetchone()
    return (row[0], row[1]) if row else None


async def create_embedding(tenant_id: int, data: EmbeddingCreate) -> EmbeddingResponse:
    """Create a new embedding.

    1. Validates embedding_type exists and is active
    2. Validates vector dimensions match embedding_type
    3. Inserts to master embedding table
    4. Inserts vector to child table in mimir_vectors schema
    """
    # Get embedding type info
    type_info = await _get_embedding_type_info(data.embedding_type)
    if not type_info:
        raise ValueError(
            f"Embedding type '{data.embedding_type}' not found or inactive"
        )

    expected_dims, vector_table = type_info
    actual_dims = len(data.embedding)

    if actual_dims != expected_dims:
        raise ValueError(
            f"Embedding dimensions mismatch: {data.embedding_type} expects {expected_dims}, got {actual_dims}"
        )

    embedding_id = uuid4()
    vector_str = "[" + ",".join(str(v) for v in data.embedding) + "]"

    async with get_connection() as conn:
        # Insert to master embedding table
        result = await conn.execute(
            f"""
            INSERT INTO {SCHEMA_NAME}.embedding
                (id, tenant_id, artifact_id, embedding_type, metadata)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id, tenant_id, artifact_id, embedding_type, metadata, created_at
            """,
            (
                str(embedding_id),
                tenant_id,
                str(data.artifact_id),
                data.embedding_type,
                Json(data.metadata) if data.metadata else None,
            ),
        )
        row = await result.fetchone()

        # Insert vector to child table
        await conn.execute(
            f"""
            INSERT INTO {VECTOR_SCHEMA}.{vector_table}
                (embedding_id, embedding)
            VALUES (%s, %s::vector)
            """,
            (str(embedding_id), vector_str),
        )

        await conn.commit()

    embedding = _row_to_embedding_response(row)

    # Log provenance event
    await provenance_service.log_action(
        tenant_id=tenant_id,
        entity_type="embedding",
        entity_id=embedding.id,
        action="create",
        actor_type="api_client",
        metadata={
            "embedding_type": data.embedding_type,
            "artifact_id": str(data.artifact_id),
        },
    )

    return embedding


async def get_embedding(
    embedding_id: UUID, tenant_id: int, include_vector: bool = False
) -> EmbeddingResponse | EmbeddingWithVectorResponse | None:
    """Get embedding by UUID."""
    async with get_connection() as conn:
        result = await conn.execute(
            f"""
            SELECT e.id, e.tenant_id, e.artifact_id, e.embedding_type, e.metadata, e.created_at
            FROM {SCHEMA_NAME}.embedding e
            WHERE e.id = %s AND e.tenant_id = %s
            """,
            (str(embedding_id), tenant_id),
        )
        row = await result.fetchone()

    if not row:
        return None

    if include_vector:
        # Get vector from child table
        embedding_type = row[3]
        type_info = await _get_embedding_type_info(embedding_type)
        if type_info:
            _, vector_table = type_info
            async with get_connection() as conn:
                vec_result = await conn.execute(
                    f"""
                    SELECT embedding::text
                    FROM {VECTOR_SCHEMA}.{vector_table}
                    WHERE embedding_id = %s
                    """,
                    (str(embedding_id),),
                )
                vec_row = await vec_result.fetchone()

            if vec_row:
                vector = _parse_vector_string(vec_row[0])
                return _row_to_embedding_with_vector(row, vector)

    return _row_to_embedding_response(row)


async def list_embeddings(
    tenant_id: int,
    limit: int = 50,
    offset: int = 0,
    artifact_id: UUID | None = None,
    embedding_type: str | None = None,
) -> EmbeddingListResponse:
    """List embeddings with optional filtering."""
    async with get_connection() as conn:
        where_clause = "WHERE e.tenant_id = %s"
        params: list = [tenant_id]

        if artifact_id:
            where_clause += " AND e.artifact_id = %s"
            params.append(str(artifact_id))
        if embedding_type:
            where_clause += " AND e.embedding_type = %s"
            params.append(embedding_type)

        from_clause = f"FROM {SCHEMA_NAME}.embedding e"

        # Get count
        count_result = await conn.execute(
            f"SELECT COUNT(*) {from_clause} {where_clause}",
            params,
        )
        total = (await count_result.fetchone())[0]

        # Get embeddings
        result = await conn.execute(
            f"""
            SELECT e.id, e.tenant_id, e.artifact_id, e.embedding_type, e.metadata, e.created_at
            {from_clause}
            {where_clause}
            ORDER BY e.created_at DESC
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
    embedding_type: str | None = None,
) -> list[EmbeddingResponse]:
    """Get all embeddings for an artifact."""
    async with get_connection() as conn:
        where_clause = "WHERE e.tenant_id = %s AND e.artifact_id = %s"
        params: list = [tenant_id, str(artifact_id)]

        if embedding_type:
            where_clause += " AND e.embedding_type = %s"
            params.append(embedding_type)

        result = await conn.execute(
            f"""
            SELECT e.id, e.tenant_id, e.artifact_id, e.embedding_type, e.metadata, e.created_at
            FROM {SCHEMA_NAME}.embedding e
            {where_clause}
            ORDER BY e.created_at DESC
            """,
            params,
        )
        rows = await result.fetchall()

    return [_row_to_embedding_response(row) for row in rows]


async def find_similar(
    tenant_id: int,
    query_vector: list[float],
    embedding_type: str,
    limit: int = 20,
    artifact_types: list[str] | None = None,
    similarity_threshold: float = 0.0,
) -> SimilaritySearchResponse:
    """Find embeddings similar to query vector using cosine distance."""
    # Get vector table name
    type_info = await _get_embedding_type_info(embedding_type)
    if not type_info:
        raise ValueError(f"Embedding type '{embedding_type}' not found or inactive")

    expected_dims, vector_table = type_info
    if len(query_vector) != expected_dims:
        raise ValueError(
            f"Query vector dimensions mismatch: {embedding_type} expects {expected_dims}, got {len(query_vector)}"
        )

    vector_str = "[" + ",".join(str(v) for v in query_vector) + "]"

    async with get_connection() as conn:
        where_clause = "WHERE e.tenant_id = %s"
        params: list = [tenant_id]

        if artifact_types:
            join_clause = f"JOIN {SCHEMA_NAME}.artifact a ON e.artifact_id = a.id"
        if artifact_types:
            where_clause += " AND a.artifact_type = ANY(%s)"
            params.append(artifact_types)
        else:
            join_clause = ""

        # Use cosine distance (<=> operator)
        # Note: vector_str must come first for the SELECT clause similarity calc
        result = await conn.execute(
            f"""
            SELECT e.id, e.artifact_id, e.embedding_type,
                   1 - (v.embedding <=> %s::vector) as similarity
            FROM {SCHEMA_NAME}.embedding e
            JOIN {VECTOR_SCHEMA}.{vector_table} v ON v.embedding_id = e.id
            {join_clause}
            {where_clause}
            ORDER BY v.embedding <=> %s::vector
            LIMIT %s
            """,
            [vector_str] + params + [vector_str, limit],
        )
        rows = await result.fetchall()

    results = []
    for row in rows:
        similarity = row[3]
        if similarity >= similarity_threshold:
            results.append(
                SimilarityResult(
                    embedding_id=UUID(row[0]) if isinstance(row[0], str) else row[0],
                    artifact_id=UUID(row[1]) if isinstance(row[1], str) else row[1],
                    embedding_type=row[2],
                    similarity=similarity,
                )
            )

    return SimilaritySearchResponse(results=results, total=len(results))


async def check_embedding_exists(
    tenant_id: int,
    artifact_id: UUID,
    embedding_type: str,
) -> bool:
    """Check if embedding already exists for artifact/type combination."""
    async with get_connection() as conn:
        result = await conn.execute(
            f"""
            SELECT 1 FROM {SCHEMA_NAME}.embedding
            WHERE tenant_id = %s AND artifact_id = %s AND embedding_type = %s
            """,
            (tenant_id, str(artifact_id), embedding_type),
        )
        row = await result.fetchone()

    return row is not None


def _row_to_embedding_response(row: tuple) -> EmbeddingResponse:
    """Convert database row to EmbeddingResponse."""
    return EmbeddingResponse(
        id=UUID(row[0]) if isinstance(row[0], str) else row[0],
        tenant_id=row[1],
        artifact_id=UUID(row[2]) if isinstance(row[2], str) else row[2],
        embedding_type=row[3],
        metadata=row[4],
        created_at=row[5],
    )


def _row_to_embedding_with_vector(
    row: tuple, vector: list[float]
) -> EmbeddingWithVectorResponse:
    """Convert database row with vector to EmbeddingWithVectorResponse."""
    return EmbeddingWithVectorResponse(
        id=UUID(row[0]) if isinstance(row[0], str) else row[0],
        tenant_id=row[1],
        artifact_id=UUID(row[2]) if isinstance(row[2], str) else row[2],
        embedding_type=row[3],
        metadata=row[4],
        created_at=row[5],
        embedding=vector,
        dimensions=len(vector),
    )


def _parse_vector_string(vector_str: str) -> list[float]:
    """Parse vector string: '[1.0,2.0,3.0]' -> [1.0, 2.0, 3.0]"""
    return [float(v) for v in vector_str.strip("[]").split(",")]


# NOTE: delete_embedding removed - embeddings are append-only
