"""Embedding type service - manages embedding model vocabulary and vector tables.

This service:
1. Creates embedding_type records in mimirdata schema
2. Creates corresponding vector tables in mimir_vectors schema
3. Manages HNSW indexes for each embedding type
"""

from mimir.database import get_connection
from mimir.schemas.embedding_type import (
    EmbeddingTypeCreate,
    EmbeddingTypeListResponse,
    EmbeddingTypeResponse,
)

SCHEMA_NAME = "mimirdata"
VECTOR_SCHEMA = "mimir_vectors"


def _get_distance_ops(metric: str) -> str:
    """Get pgvector operator class for distance metric."""
    return {
        "cosine": "vector_cosine_ops",
        "l2": "vector_l2_ops",
        "inner_product": "vector_ip_ops",
    }.get(metric, "vector_cosine_ops")


def _code_to_table_name(code: str) -> str:
    """Convert embedding type code to vector table name."""
    return f"vec_{code.replace('-', '_')}"


async def create_embedding_type(data: EmbeddingTypeCreate) -> EmbeddingTypeResponse:
    """Create a new embedding type and its vector table."""
    table_name = _code_to_table_name(data.code)

    async with get_connection() as conn:
        # 1. Insert into embedding_type vocabulary table
        result = await conn.execute(
            f"""
            INSERT INTO {SCHEMA_NAME}.embedding_type
                (code, display_name, provider, dimensions, distance_metric,
                 max_tokens, description, vector_table_name)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING code, display_name, provider, dimensions, distance_metric,
                      max_tokens, description, vector_table_name, is_active,
                      sort_order, created_at
            """,
            (
                data.code,
                data.display_name,
                data.provider,
                data.dimensions,
                data.distance_metric,
                data.max_tokens,
                data.description,
                table_name,
            ),
        )
        row = await result.fetchone()

        # 2. Create vector table in mimir_vectors schema
        # Note: Using f-string is safe here because code is validated by regex pattern
        await conn.execute(f"""
            CREATE TABLE {VECTOR_SCHEMA}.{table_name} (
                embedding_id UUID PRIMARY KEY
                    REFERENCES {SCHEMA_NAME}.embedding(id) ON DELETE CASCADE,
                embedding vector({data.dimensions}) NOT NULL
            )
        """)

        # 3. Create HNSW index
        ops = _get_distance_ops(data.distance_metric)
        await conn.execute(f"""
            CREATE INDEX idx_{table_name}_hnsw
                ON {VECTOR_SCHEMA}.{table_name}
                USING hnsw (embedding {ops})
                WITH (m = 16, ef_construction = 64)
        """)

        await conn.commit()

    return _row_to_embedding_type_response(row)


async def get_embedding_type(code: str) -> EmbeddingTypeResponse | None:
    """Get embedding type by code."""
    async with get_connection() as conn:
        result = await conn.execute(
            f"""
            SELECT code, display_name, provider, dimensions, distance_metric,
                   max_tokens, description, vector_table_name, is_active,
                   sort_order, created_at
            FROM {SCHEMA_NAME}.embedding_type
            WHERE code = %s
            """,
            (code,),
        )
        row = await result.fetchone()

    if not row:
        return None
    return _row_to_embedding_type_response(row)


async def list_embedding_types(
    active_only: bool = True,
    provider: str | None = None,
) -> EmbeddingTypeListResponse:
    """List all embedding types."""
    async with get_connection() as conn:
        where_clauses = []
        params: list = []

        if active_only:
            where_clauses.append("is_active = true")
        if provider:
            where_clauses.append("provider = %s")
            params.append(provider)

        where_sql = ""
        if where_clauses:
            where_sql = "WHERE " + " AND ".join(where_clauses)

        result = await conn.execute(
            f"""
            SELECT code, display_name, provider, dimensions, distance_metric,
                   max_tokens, description, vector_table_name, is_active,
                   sort_order, created_at
            FROM {SCHEMA_NAME}.embedding_type
            {where_sql}
            ORDER BY sort_order, code
            """,
            params,
        )
        rows = await result.fetchall()

    items = [_row_to_embedding_type_response(row) for row in rows]
    return EmbeddingTypeListResponse(items=items, total=len(items))


async def deactivate_embedding_type(code: str) -> bool:
    """Soft delete (deactivate) an embedding type."""
    async with get_connection() as conn:
        result = await conn.execute(
            f"""
            UPDATE {SCHEMA_NAME}.embedding_type
            SET is_active = false
            WHERE code = %s
            RETURNING code
            """,
            (code,),
        )
        row = await result.fetchone()
        await conn.commit()

    return row is not None


def _row_to_embedding_type_response(row: tuple) -> EmbeddingTypeResponse:
    """Convert database row to EmbeddingTypeResponse."""
    return EmbeddingTypeResponse(
        code=row[0],
        display_name=row[1],
        provider=row[2],
        dimensions=row[3],
        distance_metric=row[4],
        max_tokens=row[5],
        description=row[6],
        vector_table_name=row[7],
        is_active=row[8],
        sort_order=row[9],
        created_at=row[10],
    )
