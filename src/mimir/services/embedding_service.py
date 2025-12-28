"""Embedding service - generate and store vector embeddings.

Uses pluggable providers for embedding generation. Supports multiple providers
including Voyage AI (Anthropic recommended) and OpenAI.
"""

import json

import structlog

from mimir.config import get_settings
from mimir.database import get_connection
from mimir.models import SCHEMA_NAME
from mimir.schemas.embedding import (
    MAX_EMBEDDING_DIMENSIONS,
    EmbeddingBatchCreate,
    EmbeddingBatchResponse,
    EmbeddingCreate,
    EmbeddingListResponse,
    EmbeddingModelResponse,
    EmbeddingProvidersResponse,
    EmbeddingResponse,
)
from mimir.services.embedding_providers.base import EmbeddingModelInfo
from mimir.services.embedding_providers.registry import (
    get_default_model,
    get_model_info,
    get_provider_for_model,
    list_all_models,
    list_providers,
)

logger = structlog.get_logger()


def _model_info_to_response(info: EmbeddingModelInfo) -> EmbeddingModelResponse:
    """Convert internal model info to API response schema."""
    return EmbeddingModelResponse(
        model_id=info.model_id,
        provider=info.provider,
        display_name=info.display_name,
        dimensions=info.dimensions,
        max_tokens=info.max_tokens,
        description=info.description,
    )


async def get_available_providers() -> EmbeddingProvidersResponse:
    """Get available embedding providers and models.

    Returns:
        Response with providers, models, and default model info
    """
    providers = list_providers()
    models = list_all_models()
    default = get_default_model()

    # If no default from providers, check settings
    default_model_id = None
    if default:
        default_model_id = default.model_id
    else:
        settings = get_settings()
        if settings.default_embedding_model:
            default_model_id = settings.default_embedding_model

    return EmbeddingProvidersResponse(
        providers=providers,
        models=[_model_info_to_response(m) for m in models],
        default_model=default_model_id,
    )


def _get_default_model_id() -> str:
    """Get the default model ID.

    Checks settings first, then falls back to provider defaults.

    Returns:
        Model ID string

    Raises:
        ValueError: If no embedding providers are configured
    """
    settings = get_settings()

    # Check explicit setting first
    if settings.default_embedding_model:
        return settings.default_embedding_model

    # Fall back to provider default
    default = get_default_model()
    if default:
        return default.model_id

    raise ValueError(
        "No embedding model available. Configure VOYAGE_API_KEY or OPENAI_API_KEY."
    )


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
        ValueError: If artifact not found, model not supported, or provider not configured
    """
    # Determine model to use
    model_id = data.model or _get_default_model_id()

    # Get provider for the model
    provider = get_provider_for_model(model_id)
    if not provider:
        raise ValueError(f"No provider found for model: {model_id}")

    if not provider.is_configured():
        raise ValueError(
            f"Provider '{provider.provider_name}' is not configured. "
            f"Set the appropriate API key environment variable."
        )

    # Get text to embed
    if data.text:
        text = data.text
    else:
        text = await get_artifact_content(data.artifact_id, tenant_id)
        if not text:
            raise ValueError(f"Artifact {data.artifact_id} not found or has no content")

    # Generate embedding
    result = await provider.generate_embedding(text, model_id)

    dimensions = result.dimensions

    # Truncate to max dimensions if needed
    embedding = result.embedding
    if dimensions > MAX_EMBEDDING_DIMENSIONS:
        embedding = embedding[:MAX_EMBEDDING_DIMENSIONS]
        dimensions = MAX_EMBEDDING_DIMENSIONS

    # Pad embedding to max dimensions for storage
    padded_embedding = embedding + [0.0] * (MAX_EMBEDDING_DIMENSIONS - len(embedding))

    # Store in database
    async with get_connection() as conn:
        db_result = await conn.execute(
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
                model_id,
                json.dumps(padded_embedding),
                dimensions,
                data.chunk_index,
                text[:1000] if len(text) > 1000 else text,  # Store snippet
            ),
        )
        row = await db_result.fetchone()
        await conn.commit()

    await logger.ainfo(
        "Created embedding",
        artifact_id=data.artifact_id,
        model=model_id,
        provider=provider.provider_name,
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

    # Determine model to use
    model_id = data.model or _get_default_model_id()

    # Get provider for the model
    provider = get_provider_for_model(model_id)
    if not provider:
        return EmbeddingBatchResponse(
            created=0,
            failed=len(data.artifact_ids),
            errors=[f"No provider found for model: {model_id}"],
        )

    if not provider.is_configured():
        return EmbeddingBatchResponse(
            created=0,
            failed=len(data.artifact_ids),
            errors=[
                f"Provider '{provider.provider_name}' is not configured. "
                f"Set the appropriate API key environment variable."
            ],
        )

    # Get model info for dimensions
    model_info = get_model_info(model_id)

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
            # Use batch generation if provider supports it
            if provider.supports_batch():
                results = await provider.generate_embeddings_batch(texts, model_id)
            else:
                results = []
                for text in texts:
                    result = await provider.generate_embedding(text, model_id)
                    results.append(result)

            # Store all embeddings
            async with get_connection() as conn:
                for idx, (artifact_id, text) in enumerate(batch):
                    result = results[idx]
                    embedding = result.embedding
                    dimensions = result.dimensions

                    # Truncate to max dimensions if needed
                    if len(embedding) > MAX_EMBEDDING_DIMENSIONS:
                        embedding = embedding[:MAX_EMBEDDING_DIMENSIONS]
                        dimensions = MAX_EMBEDDING_DIMENSIONS

                    padded_embedding = embedding + [0.0] * (
                        MAX_EMBEDDING_DIMENSIONS - len(embedding)
                    )

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
                            model_id,
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
        model=model_id,
        provider=provider.provider_name,
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
    artifact_id: int, tenant_id: int, model: str | None = None
) -> list[float] | None:
    """Get the embedding vector for an artifact.

    Args:
        artifact_id: ID of the artifact
        tenant_id: Tenant ID for isolation
        model: Embedding model name (defaults to configured default)

    Returns:
        Embedding vector or None if not found
    """
    if model is None:
        model = _get_default_model_id()

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


async def generate_query_embedding(text: str, model: str | None = None) -> list[float]:
    """Generate an embedding for a query text.

    This is used for similarity search queries.

    Args:
        text: Query text to embed
        model: Embedding model to use (defaults to configured default)

    Returns:
        Embedding vector

    Raises:
        ValueError: If no provider configured or model not found
    """
    model_id = model or _get_default_model_id()

    provider = get_provider_for_model(model_id)
    if not provider:
        raise ValueError(f"No provider found for model: {model_id}")

    if not provider.is_configured():
        raise ValueError(
            f"Provider '{provider.provider_name}' is not configured. "
            f"Set the appropriate API key environment variable."
        )

    result = await provider.generate_embedding(text, model_id)

    embedding = result.embedding
    # Truncate if needed
    if len(embedding) > MAX_EMBEDDING_DIMENSIONS:
        embedding = embedding[:MAX_EMBEDDING_DIMENSIONS]

    return embedding
