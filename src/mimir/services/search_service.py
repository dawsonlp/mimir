"""Search service - semantic, full-text, and hybrid search."""

import json

import structlog

from mimir.database import get_connection
from mimir.models import SCHEMA_NAME
from mimir.schemas.search import (
    FulltextSearchRequest,
    SearchRequest,
    SearchResponse,
    SearchResultItem,
    SearchType,
    SemanticSearchRequest,
    SimilarArtifactsRequest,
)
from mimir.services.embedding_service import (
    generate_openai_embedding,
    get_embedding_vector,
)

logger = structlog.get_logger()


async def semantic_search(
    tenant_id: int, request: SemanticSearchRequest
) -> SearchResponse:
    """Perform semantic search using vector similarity.

    Uses pgvector's cosine distance operator (<=>) with HNSW index
    for approximate nearest neighbor search.

    Args:
        tenant_id: Tenant ID for isolation
        request: Semantic search request

    Returns:
        Search response with ranked results
    """
    # Generate embedding for the query
    query_embedding = await generate_openai_embedding(request.query, request.model)

    # Pad to 3072 dimensions for storage compatibility
    dimensions = len(query_embedding)
    padded_embedding = query_embedding + [0.0] * (3072 - dimensions)

    # Build type filter if specified
    type_filter = ""
    params: list = [tenant_id, json.dumps(padded_embedding)]

    if request.artifact_types:
        placeholders = ", ".join(["%s"] * len(request.artifact_types))
        type_filter = f"AND a.artifact_type::text IN ({placeholders})"
        params.extend(request.artifact_types)

    # Similarity threshold (convert to distance: 1 - similarity)
    distance_threshold = 1.0 - request.min_similarity
    params.append(distance_threshold)

    # Content selection based on include_content flag
    content_select = "av.content" if request.include_content else "NULL"

    async with get_connection() as conn:
        # Count total matching results
        count_result = await conn.execute(
            f"""
            SELECT COUNT(DISTINCT a.id)
            FROM {SCHEMA_NAME}.embeddings e
            JOIN {SCHEMA_NAME}.artifacts a ON e.artifact_id = a.id
            WHERE a.tenant_id = %s
            AND e.model = %s
            AND (e.embedding <=> %s::mimirdata.vector) < %s
            {type_filter.replace("a.artifact_type::text IN", "a.artifact_type::text IN") if type_filter else ""}
            """,
            [tenant_id, request.model.value, json.dumps(padded_embedding), distance_threshold]
            + (request.artifact_types if request.artifact_types else []),
        )
        total = (await count_result.fetchone())[0]

        # Search with vector similarity
        result = await conn.execute(
            f"""
            SELECT
                a.id as artifact_id,
                a.artifact_type::text,
                a.title,
                a.source,
                1 - (e.embedding <=> %s::mimirdata.vector) as similarity,
                SUBSTRING(av.content, 1, 300) as snippet,
                {content_select} as content,
                a.created_at,
                a.updated_at,
                a.metadata
            FROM {SCHEMA_NAME}.embeddings e
            JOIN {SCHEMA_NAME}.artifacts a ON e.artifact_id = a.id
            LEFT JOIN LATERAL (
                SELECT content FROM {SCHEMA_NAME}.artifact_versions
                WHERE artifact_id = a.id
                ORDER BY version_number DESC
                LIMIT 1
            ) av ON true
            WHERE a.tenant_id = %s
            AND e.model = %s
            AND (e.embedding <=> %s::mimirdata.vector) < %s
            {type_filter}
            ORDER BY e.embedding <=> %s::mimirdata.vector
            LIMIT %s OFFSET %s
            """,
            [
                json.dumps(padded_embedding),
                tenant_id,
                request.model.value,
                json.dumps(padded_embedding),
                distance_threshold,
            ]
            + (request.artifact_types if request.artifact_types else [])
            + [json.dumps(padded_embedding), request.limit, request.offset],
        )
        rows = await result.fetchall()

    items = [
        SearchResultItem(
            artifact_id=row[0],
            artifact_type=row[1],
            title=row[2],
            source=row[3],
            score=float(row[4]),  # Use similarity as score
            similarity=float(row[4]),
            rank=None,
            content_snippet=row[5],
            content=row[6],
            created_at=row[7],
            updated_at=row[8],
            metadata=row[9],
        )
        for row in rows
    ]

    await logger.ainfo(
        "Semantic search completed",
        query_length=len(request.query),
        model=request.model.value,
        results=len(items),
        total=total,
    )

    return SearchResponse(
        items=items,
        total=total,
        query=request.query,
        search_type=SearchType.SEMANTIC,
        limit=request.limit,
        offset=request.offset,
    )


async def fulltext_search(
    tenant_id: int, request: FulltextSearchRequest
) -> SearchResponse:
    """Perform full-text search using PostgreSQL tsvector/tsquery.

    Uses GIN indexes for efficient full-text search with ranking.

    Args:
        tenant_id: Tenant ID for isolation
        request: Full-text search request

    Returns:
        Search response with ranked results
    """
    # Convert query to tsquery format
    # Split words and join with & for AND logic
    query_words = request.query.split()
    tsquery = " & ".join(query_words)

    # Build type filter if specified
    type_filter = ""
    params: list = [tenant_id]

    if request.artifact_types:
        placeholders = ", ".join(["%s"] * len(request.artifact_types))
        type_filter = f"AND a.artifact_type::text IN ({placeholders})"
        params.extend(request.artifact_types)

    # Build search conditions based on where to search
    search_conditions = []
    if request.search_title:
        search_conditions.append("a.search_vector @@ to_tsquery('english', %s)")
    if request.search_content:
        search_conditions.append("av.search_vector @@ to_tsquery('english', %s)")

    if not search_conditions:
        # Default to both if neither specified
        search_conditions = [
            "a.search_vector @@ to_tsquery('english', %s)",
            "av.search_vector @@ to_tsquery('english', %s)",
        ]

    search_clause = " OR ".join(search_conditions)

    # Content selection based on include_content flag
    content_select = "av.content" if request.include_content else "NULL"

    async with get_connection() as conn:
        # Count total matching results
        count_params = params + [tsquery] * len(search_conditions)
        count_result = await conn.execute(
            f"""
            SELECT COUNT(DISTINCT a.id)
            FROM {SCHEMA_NAME}.artifacts a
            LEFT JOIN LATERAL (
                SELECT content, search_vector FROM {SCHEMA_NAME}.artifact_versions
                WHERE artifact_id = a.id
                ORDER BY version_number DESC
                LIMIT 1
            ) av ON true
            WHERE a.tenant_id = %s
            {type_filter}
            AND ({search_clause})
            """,
            count_params,
        )
        total = (await count_result.fetchone())[0]

        # Search with ranking
        # Build rank calculation based on what we're searching
        rank_parts = []
        if request.search_title:
            rank_parts.append(
                "ts_rank(a.search_vector, to_tsquery('english', %s))"
            )
        if request.search_content:
            rank_parts.append(
                "ts_rank(av.search_vector, to_tsquery('english', %s))"
            )
        if not rank_parts:
            rank_parts = [
                "ts_rank(a.search_vector, to_tsquery('english', %s))",
                "ts_rank(av.search_vector, to_tsquery('english', %s))",
            ]

        rank_calc = " + ".join(rank_parts)

        (
            params
            + [tsquery] * len(rank_parts)  # For rank calculation
            + [tsquery] * len(search_conditions)  # For WHERE clause
            + [request.limit, request.offset]
        )

        result = await conn.execute(
            f"""
            SELECT
                a.id as artifact_id,
                a.artifact_type::text,
                a.title,
                a.source,
                ({rank_calc}) as rank,
                ts_headline('english', COALESCE(av.content, ''),
                           to_tsquery('english', %s),
                           'MaxWords=50, MinWords=25') as snippet,
                {content_select} as content,
                a.created_at,
                a.updated_at,
                a.metadata
            FROM {SCHEMA_NAME}.artifacts a
            LEFT JOIN LATERAL (
                SELECT content, search_vector FROM {SCHEMA_NAME}.artifact_versions
                WHERE artifact_id = a.id
                ORDER BY version_number DESC
                LIMIT 1
            ) av ON true
            WHERE a.tenant_id = %s
            {type_filter}
            AND ({search_clause})
            ORDER BY ({rank_calc}) DESC
            LIMIT %s OFFSET %s
            """,
            params
            + [tsquery] * len(rank_parts)  # For rank calculation in SELECT
            + [tsquery]  # For ts_headline
            + [tenant_id]  # tenant_id for WHERE
            + (request.artifact_types if request.artifact_types else [])
            + [tsquery] * len(search_conditions)  # For WHERE clause
            + [tsquery] * len(rank_parts)  # For ORDER BY
            + [request.limit, request.offset],
        )
        rows = await result.fetchall()

    items = [
        SearchResultItem(
            artifact_id=row[0],
            artifact_type=row[1],
            title=row[2],
            source=row[3],
            score=float(row[4]) if row[4] else 0.0,
            similarity=None,
            rank=float(row[4]) if row[4] else 0.0,
            content_snippet=row[5],
            content=row[6],
            created_at=row[7],
            updated_at=row[8],
            metadata=row[9],
        )
        for row in rows
    ]

    await logger.ainfo(
        "Full-text search completed",
        query=request.query,
        results=len(items),
        total=total,
    )

    return SearchResponse(
        items=items,
        total=total,
        query=request.query,
        search_type=SearchType.FULLTEXT,
        limit=request.limit,
        offset=request.offset,
    )


async def hybrid_search(
    tenant_id: int, request: SearchRequest
) -> SearchResponse:
    """Perform hybrid search combining semantic and full-text search.

    Uses Reciprocal Rank Fusion (RRF) to combine rankings from both
    search methods for better overall results.

    RRF formula: score = sum(1 / (k + rank)) where k=60 is typical

    Args:
        tenant_id: Tenant ID for isolation
        request: Hybrid search request

    Returns:
        Search response with combined ranked results
    """
    # Generate embedding for semantic search
    query_embedding = await generate_openai_embedding(request.query, request.model)
    dimensions = len(query_embedding)
    padded_embedding = query_embedding + [0.0] * (3072 - dimensions)

    # Convert query to tsquery for FTS
    query_words = request.query.split()
    tsquery = " & ".join(query_words)

    # Build type filter
    type_filter = ""
    type_params: list = []
    if request.artifact_types:
        placeholders = ", ".join(["%s"] * len(request.artifact_types))
        type_filter = f"AND a.artifact_type::text IN ({placeholders})"
        type_params = request.artifact_types

    # Distance threshold for semantic search
    distance_threshold = 1.0 - request.min_similarity

    # Content selection
    content_select = "av.content" if request.include_content else "NULL"

    # RRF constant (k=60 is standard)
    k = 60

    async with get_connection() as conn:
        # Use CTE to combine semantic and FTS results with RRF
        result = await conn.execute(
            f"""
            WITH semantic_results AS (
                SELECT
                    a.id as artifact_id,
                    ROW_NUMBER() OVER (ORDER BY e.embedding <=> %s::mimirdata.vector) as semantic_rank,
                    1 - (e.embedding <=> %s::mimirdata.vector) as similarity
                FROM {SCHEMA_NAME}.embeddings e
                JOIN {SCHEMA_NAME}.artifacts a ON e.artifact_id = a.id
                WHERE a.tenant_id = %s
                AND e.model = %s
                AND (e.embedding <=> %s::mimirdata.vector) < %s
                {type_filter}
            ),
            fts_results AS (
                SELECT
                    a.id as artifact_id,
                    ROW_NUMBER() OVER (ORDER BY ts_rank(
                        COALESCE(a.search_vector, ''::tsvector) ||
                        COALESCE(av.search_vector, ''::tsvector),
                        to_tsquery('english', %s)
                    ) DESC) as fts_rank,
                    ts_rank(
                        COALESCE(a.search_vector, ''::tsvector) ||
                        COALESCE(av.search_vector, ''::tsvector),
                        to_tsquery('english', %s)
                    ) as rank
                FROM {SCHEMA_NAME}.artifacts a
                LEFT JOIN LATERAL (
                    SELECT search_vector FROM {SCHEMA_NAME}.artifact_versions
                    WHERE artifact_id = a.id
                    ORDER BY version_number DESC
                    LIMIT 1
                ) av ON true
                WHERE a.tenant_id = %s
                {type_filter}
                AND (
                    a.search_vector @@ to_tsquery('english', %s)
                    OR av.search_vector @@ to_tsquery('english', %s)
                )
            ),
            combined AS (
                SELECT
                    COALESCE(s.artifact_id, f.artifact_id) as artifact_id,
                    COALESCE(1.0 / (%s + s.semantic_rank), 0) +
                    COALESCE(1.0 / (%s + f.fts_rank), 0) as rrf_score,
                    s.similarity,
                    f.rank as fts_rank
                FROM semantic_results s
                FULL OUTER JOIN fts_results f ON s.artifact_id = f.artifact_id
            )
            SELECT
                c.artifact_id,
                a.artifact_type::text,
                a.title,
                a.source,
                c.rrf_score as score,
                c.similarity,
                c.fts_rank,
                SUBSTRING(av.content, 1, 300) as snippet,
                {content_select} as content,
                a.created_at,
                a.updated_at,
                a.metadata
            FROM combined c
            JOIN {SCHEMA_NAME}.artifacts a ON c.artifact_id = a.id
            LEFT JOIN LATERAL (
                SELECT content FROM {SCHEMA_NAME}.artifact_versions
                WHERE artifact_id = a.id
                ORDER BY version_number DESC
                LIMIT 1
            ) av ON true
            ORDER BY c.rrf_score DESC
            LIMIT %s OFFSET %s
            """,
            [
                # semantic_results CTE
                json.dumps(padded_embedding),  # ORDER BY
                json.dumps(padded_embedding),  # similarity calc
                tenant_id,
                request.model.value,
                json.dumps(padded_embedding),  # distance comparison
                distance_threshold,
            ]
            + type_params
            + [
                # fts_results CTE
                tsquery,  # ROW_NUMBER rank
                tsquery,  # rank calc
                tenant_id,
            ]
            + type_params
            + [
                tsquery,  # WHERE clause 1
                tsquery,  # WHERE clause 2
                # combined CTE
                k,  # RRF k for semantic
                k,  # RRF k for fts
                # Final query
                request.limit,
                request.offset,
            ],
        )
        rows = await result.fetchall()

        # Get total count (approximate for hybrid)
        count_result = await conn.execute(
            f"""
            SELECT COUNT(DISTINCT artifact_id) FROM (
                SELECT a.id as artifact_id
                FROM {SCHEMA_NAME}.embeddings e
                JOIN {SCHEMA_NAME}.artifacts a ON e.artifact_id = a.id
                WHERE a.tenant_id = %s
                AND e.model = %s
                AND (e.embedding <=> %s::mimirdata.vector) < %s
                {type_filter}
                UNION
                SELECT a.id as artifact_id
                FROM {SCHEMA_NAME}.artifacts a
                LEFT JOIN LATERAL (
                    SELECT search_vector FROM {SCHEMA_NAME}.artifact_versions
                    WHERE artifact_id = a.id
                    ORDER BY version_number DESC
                    LIMIT 1
                ) av ON true
                WHERE a.tenant_id = %s
                {type_filter}
                AND (
                    a.search_vector @@ to_tsquery('english', %s)
                    OR av.search_vector @@ to_tsquery('english', %s)
                )
            ) combined
            """,
            [
                tenant_id,
                request.model.value,
                json.dumps(padded_embedding),
                distance_threshold,
            ]
            + type_params
            + [tenant_id]
            + type_params
            + [tsquery, tsquery],
        )
        total = (await count_result.fetchone())[0]

    items = [
        SearchResultItem(
            artifact_id=row[0],
            artifact_type=row[1],
            title=row[2],
            source=row[3],
            score=float(row[4]) if row[4] else 0.0,
            similarity=float(row[5]) if row[5] else None,
            rank=float(row[6]) if row[6] else None,
            content_snippet=row[7],
            content=row[8],
            created_at=row[9],
            updated_at=row[10],
            metadata=row[11],
        )
        for row in rows
    ]

    await logger.ainfo(
        "Hybrid search completed",
        query=request.query,
        model=request.model.value,
        results=len(items),
        total=total,
    )

    return SearchResponse(
        items=items,
        total=total,
        query=request.query,
        search_type=SearchType.HYBRID,
        limit=request.limit,
        offset=request.offset,
    )


async def search(tenant_id: int, request: SearchRequest) -> SearchResponse:
    """Unified search endpoint that delegates to appropriate search type.

    Args:
        tenant_id: Tenant ID for isolation
        request: Search request with type specification

    Returns:
        Search response with ranked results
    """
    if request.search_type == SearchType.SEMANTIC:
        semantic_request = SemanticSearchRequest(
            query=request.query,
            model=request.model,
            limit=request.limit,
            offset=request.offset,
            artifact_types=request.artifact_types,
            min_similarity=request.min_similarity,
            include_content=request.include_content,
        )
        return await semantic_search(tenant_id, semantic_request)

    elif request.search_type == SearchType.FULLTEXT:
        fts_request = FulltextSearchRequest(
            query=request.query,
            limit=request.limit,
            offset=request.offset,
            artifact_types=request.artifact_types,
            include_content=request.include_content,
        )
        return await fulltext_search(tenant_id, fts_request)

    else:  # HYBRID
        return await hybrid_search(tenant_id, request)


async def find_similar_artifacts(
    tenant_id: int, request: SimilarArtifactsRequest
) -> SearchResponse:
    """Find artifacts similar to a given artifact.

    Uses the existing embedding for the artifact to find similar ones.

    Args:
        tenant_id: Tenant ID for isolation
        request: Similar artifacts request

    Returns:
        Search response with similar artifacts
    """
    # Get the embedding for the source artifact
    embedding = await get_embedding_vector(
        request.artifact_id, tenant_id, request.model.value
    )

    if not embedding:
        await logger.awarning(
            "No embedding found for artifact",
            artifact_id=request.artifact_id,
            model=request.model.value,
        )
        return SearchResponse(
            items=[],
            total=0,
            query=f"similar to artifact {request.artifact_id}",
            search_type=SearchType.SEMANTIC,
            limit=request.limit,
            offset=0,
        )

    # Pad embedding
    padded_embedding = embedding + [0.0] * (3072 - len(embedding))
    distance_threshold = 1.0 - request.min_similarity

    # Content selection
    content_select = "av.content" if request.include_content else "NULL"

    async with get_connection() as conn:
        result = await conn.execute(
            f"""
            SELECT
                a.id as artifact_id,
                a.artifact_type::text,
                a.title,
                a.source,
                1 - (e.embedding <=> %s::mimirdata.vector) as similarity,
                SUBSTRING(av.content, 1, 300) as snippet,
                {content_select} as content,
                a.created_at,
                a.updated_at,
                a.metadata
            FROM {SCHEMA_NAME}.embeddings e
            JOIN {SCHEMA_NAME}.artifacts a ON e.artifact_id = a.id
            LEFT JOIN LATERAL (
                SELECT content FROM {SCHEMA_NAME}.artifact_versions
                WHERE artifact_id = a.id
                ORDER BY version_number DESC
                LIMIT 1
            ) av ON true
            WHERE a.tenant_id = %s
            AND e.model = %s
            AND e.artifact_id != %s
            AND (e.embedding <=> %s::mimirdata.vector) < %s
            ORDER BY e.embedding <=> %s::mimirdata.vector
            LIMIT %s
            """,
            [
                json.dumps(padded_embedding),
                tenant_id,
                request.model.value,
                request.artifact_id,  # Exclude source artifact
                json.dumps(padded_embedding),
                distance_threshold,
                json.dumps(padded_embedding),
                request.limit,
            ],
        )
        rows = await result.fetchall()

    items = [
        SearchResultItem(
            artifact_id=row[0],
            artifact_type=row[1],
            title=row[2],
            source=row[3],
            score=float(row[4]),
            similarity=float(row[4]),
            rank=None,
            content_snippet=row[5],
            content=row[6],
            created_at=row[7],
            updated_at=row[8],
            metadata=row[9],
        )
        for row in rows
    ]

    await logger.ainfo(
        "Similar artifacts search completed",
        source_artifact=request.artifact_id,
        model=request.model.value,
        results=len(items),
    )

    return SearchResponse(
        items=items,
        total=len(items),
        query=f"similar to artifact {request.artifact_id}",
        search_type=SearchType.SEMANTIC,
        limit=request.limit,
        offset=0,
    )
