"""Search service - fulltext, semantic, and hybrid search (V2.1).

V2.1 Changes:
- Semantic search now requires embedding_type parameter
- Vectors are queried from mimir_vectors.vec_{type} child tables
- Uses artifact_id instead of entity_id/entity_type
"""

from enum import Enum
from uuid import UUID

from mimir.database import get_connection
from mimir.schemas.artifact import ArtifactResponse
from mimir.schemas.search import SearchResponse, SearchResult

SCHEMA_NAME = "mimirdata"
VECTOR_SCHEMA = "mimir_vectors"


class RelationDirection(str, Enum):
    """Direction for relation-based filtering."""
    
    INCOMING = "incoming"   # Artifact is target (others point to it)
    OUTGOING = "outgoing"   # Artifact is source (points to others)
    BOTH = "both"           # Either direction


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


async def get_related_artifact_ids(
    tenant_id: int,
    related_to: UUID,
    relation_type: str | None = None,
    direction: RelationDirection = RelationDirection.BOTH,
) -> set[UUID]:
    """Get artifact IDs that have a relation to/from the specified artifact.
    
    Args:
        tenant_id: Tenant ID for isolation
        related_to: UUID of the anchor artifact
        relation_type: Optional filter by relation type
        direction: incoming (anchor is target), outgoing (anchor is source), or both
    
    Returns:
        Set of artifact UUIDs that are related to the anchor artifact
    """
    async with get_connection() as conn:
        conditions = ["tenant_id = %s"]
        params: list = [tenant_id]
        
        # Build direction conditions
        direction_parts = []
        if direction in (RelationDirection.OUTGOING, RelationDirection.BOTH):
            direction_parts.append("source_id = %s")
            params.append(str(related_to))
        if direction in (RelationDirection.INCOMING, RelationDirection.BOTH):
            direction_parts.append("target_id = %s")
            params.append(str(related_to))
        
        if direction_parts:
            conditions.append(f"({' OR '.join(direction_parts)})")
        
        if relation_type:
            conditions.append("relation_type = %s")
            params.append(relation_type)
        
        where_clause = " AND ".join(conditions)
        
        # Select the "other" artifact ID based on which side matches
        result = await conn.execute(
            f"""
            SELECT DISTINCT
                CASE 
                    WHEN source_id = %s THEN target_id
                    ELSE source_id
                END as related_id
            FROM {SCHEMA_NAME}.relation
            WHERE {where_clause}
            """,
            [str(related_to)] + params,
        )
        rows = await result.fetchall()
    
    return {UUID(row[0]) if isinstance(row[0], str) else row[0] for row in rows}


def _filter_results_by_relation(
    results: list[SearchResult],
    related_ids: set[UUID],
) -> list[SearchResult]:
    """Filter search results to only include artifacts in the related set.
    
    Preserves original scores and re-ranks filtered results.
    """
    filtered = [r for r in results if r.artifact.id in related_ids]
    
    # Re-assign ranks after filtering
    for i, result in enumerate(filtered):
        result.rank = i + 1
    
    return filtered


async def fulltext_search(
    tenant_id: int,
    query: str,
    artifact_types: list[str] | None = None,
    limit: int = 20,
    offset: int = 0,
) -> SearchResponse:
    """Full-text search using PostgreSQL FTS."""
    async with get_connection() as conn:
        where_clause = "WHERE tenant_id = %s AND search_vector @@ plainto_tsquery('english', %s)"
        params: list = [tenant_id, query]

        if artifact_types:
            placeholders = ",".join(["%s"] * len(artifact_types))
            where_clause += f" AND artifact_type IN ({placeholders})"
            params.extend(artifact_types)

        # Get count
        count_result = await conn.execute(
            f"SELECT COUNT(*) FROM {SCHEMA_NAME}.artifact {where_clause}",
            params,
        )
        total = (await count_result.fetchone())[0]

        # Get results with ranking
        # Note: params for SELECT clause come before WHERE clause params
        result = await conn.execute(
            f"""
            SELECT id, tenant_id, artifact_type, parent_artifact_id,
                   start_offset, end_offset, position_metadata,
                   title, content, content_hash,
                   source, source_system, external_id, metadata,
                   created_at,
                   ts_rank(search_vector, plainto_tsquery('english', %s)) as rank
            FROM {SCHEMA_NAME}.artifact
            {where_clause}
            ORDER BY rank DESC
            LIMIT %s OFFSET %s
            """,
            [query] + params + [limit, offset],
        )
        rows = await result.fetchall()

    results = []
    for i, row in enumerate(rows):
        artifact = _row_to_artifact_response(row[:15])
        rank_score = float(row[15])
        results.append(SearchResult(artifact=artifact, score=rank_score, rank=i + 1))

    return SearchResponse(results=results, total=total, query=query)


async def semantic_search(
    tenant_id: int,
    query_vector: list[float],
    embedding_type: str,
    artifact_types: list[str] | None = None,
    limit: int = 20,
    similarity_threshold: float = 0.0,
) -> SearchResponse:
    """Semantic search using vector similarity.
    
    V2.1: Now requires embedding_type to know which vector table to search.
    """
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
        # Join embedding master table with vector child table and artifact
        where_clause = "WHERE e.tenant_id = %s"
        params: list = [tenant_id]

        if artifact_types:
            placeholders = ",".join(["%s"] * len(artifact_types))
            where_clause += f" AND a.artifact_type IN ({placeholders})"
            params.extend(artifact_types)

        result = await conn.execute(
            f"""
            SELECT DISTINCT ON (a.id)
                   a.id, a.tenant_id, a.artifact_type, a.parent_artifact_id,
                   a.start_offset, a.end_offset, a.position_metadata,
                   a.title, a.content, a.content_hash,
                   a.source, a.source_system, a.external_id, a.metadata,
                   a.created_at,
                   1 - (v.embedding <=> %s::vector) as similarity
            FROM {SCHEMA_NAME}.embedding e
            JOIN {VECTOR_SCHEMA}.{vector_table} v ON v.embedding_id = e.id
            JOIN {SCHEMA_NAME}.artifact a ON a.id = e.artifact_id
            {where_clause}
            ORDER BY a.id, similarity DESC
            """,
            params + [vector_str],
        )
        rows = await result.fetchall()

    # Filter by threshold and sort
    results = []
    for row in rows:
        similarity = float(row[15])
        if similarity >= similarity_threshold:
            artifact = _row_to_artifact_response(row[:15])
            results.append(SearchResult(artifact=artifact, score=similarity))

    # Sort by similarity
    results.sort(key=lambda r: r.score, reverse=True)
    results = results[:limit]

    # Assign ranks
    for i, result in enumerate(results):
        result.rank = i + 1

    return SearchResponse(results=results, total=len(results), query="(semantic)")


async def hybrid_search(
    tenant_id: int,
    query: str,
    query_vector: list[float],
    embedding_type: str,
    artifact_types: list[str] | None = None,
    limit: int = 20,
    rrf_k: int = 60,
    semantic_weight: float = 0.5,
) -> SearchResponse:
    """Hybrid search using Reciprocal Rank Fusion (RRF).
    
    V2.1: Now requires embedding_type for the semantic search component.
    """
    # Get fulltext results
    fts_response = await fulltext_search(
        tenant_id=tenant_id,
        query=query,
        artifact_types=artifact_types,
        limit=limit * 2,  # Fetch more for RRF
    )

    # Get semantic results
    sem_response = await semantic_search(
        tenant_id=tenant_id,
        query_vector=query_vector,
        embedding_type=embedding_type,
        artifact_types=artifact_types,
        limit=limit * 2,
    )

    # Build rank maps
    fts_ranks = {r.artifact.id: r.rank for r in fts_response.results}
    sem_ranks = {r.artifact.id: r.rank for r in sem_response.results}

    # Collect all unique artifacts
    artifacts_map = {r.artifact.id: r.artifact for r in fts_response.results}
    artifacts_map.update({r.artifact.id: r.artifact for r in sem_response.results})

    # Calculate RRF scores
    rrf_scores = []
    fts_weight = 1 - semantic_weight

    for artifact_id, artifact in artifacts_map.items():
        fts_rank = fts_ranks.get(artifact_id)
        sem_rank = sem_ranks.get(artifact_id)

        score = 0.0
        if fts_rank is not None:
            score += fts_weight / (rrf_k + fts_rank)
        if sem_rank is not None:
            score += semantic_weight / (rrf_k + sem_rank)

        rrf_scores.append((artifact, score))

    # Sort by RRF score
    rrf_scores.sort(key=lambda x: x[1], reverse=True)

    # Build results
    results = []
    for i, (artifact, score) in enumerate(rrf_scores[:limit]):
        results.append(SearchResult(artifact=artifact, score=score, rank=i + 1))

    return SearchResponse(results=results, total=len(rrf_scores), query=query)


async def similar_artifacts(
    tenant_id: int,
    artifact_id: UUID,
    embedding_type: str,
    limit: int = 10,
    artifact_types: list[str] | None = None,
) -> SearchResponse:
    """Find artifacts similar to a given artifact using its embedding.
    
    V2.1: Now requires embedding_type to know which vector table to query.
    """
    # Get vector table name
    type_info = await _get_embedding_type_info(embedding_type)
    if not type_info:
        raise ValueError(f"Embedding type '{embedding_type}' not found or inactive")
    
    _, vector_table = type_info

    async with get_connection() as conn:
        # Get the artifact's embedding from the vector table
        result = await conn.execute(
            f"""
            SELECT v.embedding::text 
            FROM {SCHEMA_NAME}.embedding e
            JOIN {VECTOR_SCHEMA}.{vector_table} v ON v.embedding_id = e.id
            WHERE e.tenant_id = %s AND e.artifact_id = %s AND e.embedding_type = %s
            LIMIT 1
            """,
            (tenant_id, str(artifact_id), embedding_type),
        )
        row = await result.fetchone()

    if not row:
        return SearchResponse(results=[], total=0, query=f"similar_to:{artifact_id}")

    # Parse embedding
    vector_str = row[0]
    query_vector = [float(v) for v in vector_str.strip("[]").split(",")]

    # Find similar, excluding the source artifact
    response = await semantic_search(
        tenant_id=tenant_id,
        query_vector=query_vector,
        embedding_type=embedding_type,
        artifact_types=artifact_types,
        limit=limit + 1,  # +1 to account for excluding self
    )

    # Filter out the source artifact
    results = [r for r in response.results if r.artifact.id != artifact_id][:limit]

    # Re-rank
    for i, result in enumerate(results):
        result.rank = i + 1

    return SearchResponse(
        results=results,
        total=len(results),
        query=f"similar_to:{artifact_id}",
    )


def _row_to_artifact_response(row: tuple) -> ArtifactResponse:
    """Convert database row to ArtifactResponse.
    
    Row columns (15 total, no updated_at for V2 append-only):
    0: id, 1: tenant_id, 2: artifact_type, 3: parent_artifact_id,
    4: start_offset, 5: end_offset, 6: position_metadata,
    7: title, 8: content, 9: content_hash,
    10: source, 11: source_system, 12: external_id, 13: metadata,
    14: created_at
    """
    return ArtifactResponse(
        id=row[0],
        tenant_id=row[1],
        artifact_type=row[2],
        parent_artifact_id=row[3],
        start_offset=row[4],
        end_offset=row[5],
        position_metadata=row[6],
        title=row[7],
        content=row[8],
        content_hash=row[9],
        source=row[10],
        source_system=row[11],
        external_id=row[12],
        metadata=row[13],
        created_at=row[14],
    )