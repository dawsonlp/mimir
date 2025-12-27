"""Embedding service - generate and store vector embeddings."""

import json

import httpx
import structlog

from mimir.config import get_settings
from mimir.database import get_connection
from mimir.models import SCHEMA_NAME
from mimir.schemas.embedding import (
    EMBEDDING_DIMENSIONS,
    EmbeddingBatchCreate,
    EmbeddingBatchResponse,
    EmbeddingCreate,
    EmbeddingListResponse,
    EmbeddingModel,
    EmbeddingResponse,
)

logger = structlog.get_logger()

# OpenAI API endpoint
OPENAI_EMBEDDINGS_URL = "https://api.openai.com/v1/embeddings"


async def generate_openai_embedding(
    text: str, model: EmbeddingModel
) -> list[float]:
    """Generate embedding using OpenAI API.

    Args:
        text: Text to embed
        model: OpenAI embedding model to use

    Returns:
        List of float values representing the embedding

    Raises:
        ValueError: If OpenAI API key is not configured
        httpx.HTTPStatusError: If API request fails
    """
    settings = get_settings()
    if not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY not configured")

    # Map our model enum to OpenAI model names
    model_mapping = {
        EmbeddingModel.OPENAI_TEXT_EMBEDDING_3_SMALL: "text-embedding-3-small",
        EmbeddingModel.OPENAI_TEXT_EMBEDDING_3_LARGE: "text-embedding-3-large",
        EmbeddingModel.OPENAI_TEXT_EMBEDDING_ADA_002: "text-embedding-ada-002",
    }

    openai_model = model_mapping.get(model)
    if not openai_model:
        raise ValueError(f"Model {model} is not an OpenAI model")

    async with httpx.AsyncClient() as client:
        response = await client.post(
            OPENAI_EMBEDDINGS_URL,
            headers={
                "Authorization": f"Bearer {settings.openai_api_key.get_secret_value()}",
                "Content-Type": "application/json",
            },
            json={
                "input": text,
                "model": openai_model,
            },
            timeout=60.0,
        )
        response.raise_for_status()
        data = response.json()
        return data["data"][0]["embedding"]


async def generate_openai_embeddings_batch(
    texts: list[str], model: EmbeddingModel
) -> list[list[float]]:
    """Generate embeddings for multiple texts using OpenAI API.

    Args:
        texts: List of texts to embed
        model: OpenAI embedding model to use

    Returns:
        List of embeddings (one per input text)

    Raises:
        ValueError: If OpenAI API key is not configured
        httpx.HTTPStatusError: If API request fails
    """
    settings = get_settings()
    if not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY not configured")

    # Map our model enum to OpenAI model names
    model_mapping = {
        EmbeddingModel.OPENAI_TEXT_EMBEDDING_3_SMALL: "text-embedding-3-small",
        EmbeddingModel.OPENAI_TEXT_EMBEDDING_3_LARGE: "text-embedding-3-large",
        EmbeddingModel.OPENAI_TEXT_EMBEDDING_ADA_002: "text-embedding-ada-002",
    }

    openai_model = model_mapping.get(model)
    if not openai_model:
        raise ValueError(f"Model {model} is not an OpenAI model")

    async with httpx.AsyncClient() as client:
        response = await client.post(
            OPENAI_EMBEDDINGS_URL,
            headers={
                "Authorization": f"Bearer {settings.openai_api_key.get_secret_value()}",
                "Content-Type": "application/json",
            },
            json={
                "input": texts,
                "model": openai_model,
            },
            timeout=120.0,
        )
        response.raise_for_status()
        data = response.json()
        # Sort by index to maintain order
        embeddings = sorted(data["data"], key=lambda x: x["index"])
        return [e["embedding"] for e in embeddings]


async def get_artifact_content(artifact_id: int, tenant_id: int) -> str | None:
    """Get the latest content for an artifact.

    Args:
        artifact_id: ID of the artifact
        tenant_id: Tenant ID for isolation

    Returns:
        Content string or None if not found
    """
    async with get_connection() as conn:
        result = await conn.execute(
            f"""
            SELECT av.content
            FROM {SCHEMA_NAME}.artifact_versions av
            JOIN {SCHEMA_NAME}.artifacts a ON av.artifact_id = a.id
            WHERE a.id = %s AND a.tenant_id = %s
            ORDER BY av.version_number DESC
            LIMIT 1
            """,
            (artifact_id, tenant_id),
        )
        row = await result.fetchone()
        return row[0] if row else None


async def create_embedding(
    tenant_id: int, data: EmbeddingCreate
) -> EmbeddingResponse:
    """Create and store an embedding for an artifact.

    Args:
        tenant_id: Tenant ID for isolation
        data: Embedding creation data

    Returns:
        Created embedding response

    Raises:
        ValueError: If artifact not found or embedding generation fails
    """
    # Get text to embed
    if data.text:
        text = data.text
    else:
        text = await get_artifact_content(data.artifact_id, tenant_id)
        if not text:
            raise ValueError(f"Artifact {data.artifact_id} not found or has no content")

    # Generate embedding based on model type
    if data.model.value.startswith("openai-"):
        embedding = await generate_openai_embedding(text, data.model)
    else:
        # For sentence-transformers models, we'd integrate with a local model
        # For now, raise an error as we only support OpenAI
        raise ValueError(
            f"Model {data.model} not yet supported. Only OpenAI models are currently available."
        )

    dimensions = len(embedding)

    # Store in database
    # Pad embedding to max dimensions (3072) for storage
    padded_embedding = embedding + [0.0] * (3072 - dimensions)

    async with get_connection() as conn:
        result = await conn.execute(
            f"""
            INSERT INTO {SCHEMA_NAME}.embeddings
                (tenant_id, artifact_id, artifact_version_id, model, embedding,
                 dimensions, chunk_index, chunk_text)
            VALUES (%s, %s, %s, %s, %s::mimirdata.vector, %s, %s, %s)
            ON CONFLICT (artifact_id, model, chunk_index)
            DO UPDATE SET
                embedding = EXCLUDED.embedding,
                dimensions = EXCLUDED.dimensions,
                chunk_text = EXCLUDED.chunk_text,
                created_at = now()
            RETURNING id, tenant_id, artifact_id, artifact_version_id, model,
                      dimensions, chunk_index, chunk_text, created_at
            """,
            (
                tenant_id,
                data.artifact_id,
                data.artifact_version_id,
                data.model.value,
                json.dumps(padded_embedding),
                dimensions,
                data.chunk_index,
                text[:1000] if len(text) > 1000 else text,  # Store snippet
            ),
        )
        row = await result.fetchone()
        await conn.commit()

    await logger.ainfo(
        "Created embedding",
        artifact_id=data.artifact_id,
        model=data.model.value,
        dimensions=dimensions,
    )

    return EmbeddingResponse(
        id=row[0],
        tenant_id=row[1],
        artifact_id=row[2],
        artifact_version_id=row[3],
        model=row[4],
        dimensions=row[5],
        chunk_index=row[6],
        chunk_text=row[7],
        created_at=row[8],
    )


async def create_embeddings_batch(
    tenant_id: int, data: EmbeddingBatchCreate
) -> EmbeddingBatchResponse:
    """Create embeddings for multiple artifacts in batch.

    Args:
        tenant_id: Tenant ID for isolation
        data: Batch embedding creation data

    Returns:
        Batch response with counts and errors
    """
    settings = get_settings()
    created = 0
    failed = 0
    errors: list[str] = []

    # Get content for all artifacts
    artifact_texts: list[tuple[int, str]] = []
    for artifact_id in data.artifact_ids:
        content = await get_artifact_content(artifact_id, tenant_id)
        if content:
            artifact_texts.append((artifact_id, content))
        else:
            failed += 1
            errors.append(f"Artifact {artifact_id} not found or has no content")

    if not artifact_texts:
        return EmbeddingBatchResponse(created=0, failed=failed, errors=errors)

    # Process in batches
    batch_size = settings.embedding_batch_size
    for i in range(0, len(artifact_texts), batch_size):
        batch = artifact_texts[i : i + batch_size]
        texts = [t[1] for t in batch]

        try:
            if data.model.value.startswith("openai-"):
                embeddings = await generate_openai_embeddings_batch(texts, data.model)
            else:
                raise ValueError(f"Model {data.model} not yet supported")

            dimensions = EMBEDDING_DIMENSIONS[data.model]

            # Store all embeddings
            async with get_connection() as conn:
                for idx, (artifact_id, text) in enumerate(batch):
                    embedding = embeddings[idx]
                    padded_embedding = embedding + [0.0] * (3072 - dimensions)

                    await conn.execute(
                        f"""
                        INSERT INTO {SCHEMA_NAME}.embeddings
                            (tenant_id, artifact_id, model, embedding,
                             dimensions, chunk_index, chunk_text)
                        VALUES (%s, %s, %s, %s::mimirdata.vector, %s, %s, %s)
                        ON CONFLICT (artifact_id, model, chunk_index)
                        DO UPDATE SET
                            embedding = EXCLUDED.embedding,
                            dimensions = EXCLUDED.dimensions,
                            chunk_text = EXCLUDED.chunk_text,
                            created_at = now()
                        """,
                        (
                            tenant_id,
                            artifact_id,
                            data.model.value,
                            json.dumps(padded_embedding),
                            dimensions,
                            0,  # chunk_index
                            text[:1000] if len(text) > 1000 else text,
                        ),
                    )
                    created += 1
                await conn.commit()

        except Exception as e:
            # Log and record errors for this batch
            await logger.aerror(
                "Batch embedding failed",
                batch_start=i,
                batch_size=len(batch),
                error=str(e),
            )
            failed += len(batch)
            errors.append(f"Batch {i // batch_size + 1} failed: {str(e)}")

    await logger.ainfo(
        "Batch embedding complete",
        created=created,
        failed=failed,
        model=data.model.value,
    )

    return EmbeddingBatchResponse(created=created, failed=failed, errors=errors)


async def get_embedding(
    embedding_id: int, tenant_id: int
) -> EmbeddingResponse | None:
    """Get embedding by ID.

    Args:
        embedding_id: ID of the embedding
        tenant_id: Tenant ID for isolation

    Returns:
        Embedding response or None if not found
    """
    async with get_connection() as conn:
        result = await conn.execute(
            f"""
            SELECT id, tenant_id, artifact_id, artifact_version_id, model,
                   dimensions, chunk_index, chunk_text, created_at
            FROM {SCHEMA_NAME}.embeddings
            WHERE id = %s AND tenant_id = %s
            """,
            (embedding_id, tenant_id),
        )
        row = await result.fetchone()

    if not row:
        return None

    return EmbeddingResponse(
        id=row[0],
        tenant_id=row[1],
        artifact_id=row[2],
        artifact_version_id=row[3],
        model=row[4],
        dimensions=row[5],
        chunk_index=row[6],
        chunk_text=row[7],
        created_at=row[8],
    )


async def list_embeddings(
    tenant_id: int,
    page: int = 1,
    page_size: int = 20,
    artifact_id: int | None = None,
    model: str | None = None,
) -> EmbeddingListResponse:
    """List embeddings for a tenant with pagination and filtering.

    Args:
        tenant_id: Tenant ID for isolation
        page: Page number (1-indexed)
        page_size: Items per page
        artifact_id: Optional filter by artifact
        model: Optional filter by model

    Returns:
        Paginated list of embeddings
    """
    offset = (page - 1) * page_size

    async with get_connection() as conn:
        # Build query with optional filters
        where_clause = "WHERE tenant_id = %s"
        params: list = [tenant_id]

        if artifact_id is not None:
            where_clause += " AND artifact_id = %s"
            params.append(artifact_id)
        if model:
            where_clause += " AND model = %s"
            params.append(model)

        # Get total count
        count_result = await conn.execute(
            f"SELECT COUNT(*) FROM {SCHEMA_NAME}.embeddings {where_clause}",
            params,
        )
        total = (await count_result.fetchone())[0]

        # Get page of embeddings
        result = await conn.execute(
            f"""
            SELECT id, tenant_id, artifact_id, artifact_version_id, model,
                   dimensions, chunk_index, chunk_text, created_at
            FROM {SCHEMA_NAME}.embeddings
            {where_clause}
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
            """,
            params + [page_size, offset],
        )
        rows = await result.fetchall()

    items = [
        EmbeddingResponse(
            id=row[0],
            tenant_id=row[1],
            artifact_id=row[2],
            artifact_version_id=row[3],
            model=row[4],
            dimensions=row[5],
            chunk_index=row[6],
            chunk_text=row[7],
            created_at=row[8],
        )
        for row in rows
    ]

    return EmbeddingListResponse(
        items=items, total=total, page=page, page_size=page_size
    )


async def delete_embedding(embedding_id: int, tenant_id: int) -> bool:
    """Delete an embedding.

    Args:
        embedding_id: ID of the embedding to delete
        tenant_id: Tenant ID for isolation

    Returns:
        True if deleted, False if not found
    """
    async with get_connection() as conn:
        result = await conn.execute(
            f"""
            DELETE FROM {SCHEMA_NAME}.embeddings
            WHERE id = %s AND tenant_id = %s
            RETURNING id
            """,
            (embedding_id, tenant_id),
        )
        row = await result.fetchone()
        await conn.commit()

    return row is not None


async def delete_embeddings_by_artifact(artifact_id: int, tenant_id: int) -> int:
    """Delete all embeddings for an artifact.

    Args:
        artifact_id: ID of the artifact
        tenant_id: Tenant ID for isolation

    Returns:
        Number of embeddings deleted
    """
    async with get_connection() as conn:
        result = await conn.execute(
            f"""
            DELETE FROM {SCHEMA_NAME}.embeddings
            WHERE artifact_id = %s AND tenant_id = %s
            """,
            (artifact_id, tenant_id),
        )
        count = result.rowcount
        await conn.commit()

    return count


async def get_embedding_vector(
    artifact_id: int, tenant_id: int, model: str
) -> list[float] | None:
    """Get the embedding vector for an artifact.

    Args:
        artifact_id: ID of the artifact
        tenant_id: Tenant ID for isolation
        model: Embedding model name

    Returns:
        Embedding vector or None if not found
    """
    async with get_connection() as conn:
        result = await conn.execute(
            f"""
            SELECT embedding::text, dimensions
            FROM {SCHEMA_NAME}.embeddings
            WHERE artifact_id = %s AND tenant_id = %s AND model = %s AND chunk_index = 0
            """,
            (artifact_id, tenant_id, model),
        )
        row = await result.fetchone()

    if not row:
        return None

    # Parse vector string format "[1.0,2.0,...]" to list
    vector_str = row[0]
    dimensions = row[1]
    # Remove brackets and split
    vector = [float(x) for x in vector_str[1:-1].split(",")]
    # Trim to actual dimensions
    return vector[:dimensions]
