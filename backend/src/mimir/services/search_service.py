"""Search service - fulltext, semantic, and hybrid search (V2.2).

V2.2 Changes (Phase 2 Enhancement):
- All queries exclude soft-deleted artifacts (deleted_at IS NULL)
- Recursive CTE for scoping includes deleted_at IS NULL at every level

V2.2 Changes (Phase 1 Enhancement):
- All search types support offset for pagination
- Metadata filtering via JSONB containment (AND across keys, OR within arrays)
- Hierarchy scoping via recursive CTE on parent_artifact_id

V2.1 Changes:
- Semantic search now requires embedding_type parameter
- Vectors are queried from mimir_vectors.vec_{type} child tables
- Uses artifact_id instead of entity_id/entity_type
"""

import json
from uuid import UUID

from mimir.database import get_connection
from mimir.schemas.artifact import ArtifactResponse
from mimir.schemas.search import RelationDirection, SearchResponse, SearchResult

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


# =============================================================================
# Metadata Filtering (Phase 1)
# =============================================================================


def _build_metadata_filter(
    metadata_filters: dict[str, str | list[str]],
    params: list,
) -> str:
    """Build SQL WHERE clause fragment for JSONB metadata filtering.

    Semantics:
    - AND across keys: all key conditions must match
    - OR within array values: artifact matches if metadata[key] equals any value in the list
    - Scalar value: artifact matches if metadata[key] equals the value

    Uses parameterized JSONB containment operator (@>) for GIN index utilization.
    Each key-value pair generates a `metadata @> %s::jsonb` condition.
    For array values, we generate OR conditions across each value.

    Args:
        metadata_filters: dict of key -> value|list[str]
        params: mutable list of query parameters (appended to)

    Returns:
        SQL fragment like "AND (metadata @> %s::jsonb) AND (metadata @> %s::jsonb OR metadata @> %s::jsonb)"
    """
    if not metadata_filters:
        return ""

    clauses = []
    for key, value in metadata_filters.items():
        if isinstance(value, list):
            # OR within array: any value matches
            or_parts = []
            for v in value:
                or_parts.append("metadata @> %s::jsonb")
                params.append(json.dumps({key: v}))
            if or_parts:
                clauses.append(f"({' OR '.join(or_parts)})")
        else:
            # Scalar: exact match
            clauses.append("metadata @> %s::jsonb")
            params.append(json.dumps({key: value}))

    return " AND " + " AND ".join(clauses) if clauses else ""


# =============================================================================
# Hierarchy Scoping (Phase 1)
# =============================================================================


async def _resolve_scope_descendants(
    tenant_id: int,
    scope_artifact_id: UUID,
) -> set[UUID] | None:
    """Resolve all descendant artifact IDs for a given scope anchor using recursive CTE.

    Includes the scope anchor itself. Returns None if the scope anchor does not exist
    (callers treat None as "no results").

    The CTE includes tenant_id filtering at every recursion level for multi-tenant safety.
    Includes a forward-compatible deleted_at IS NULL filter — currently a no-op since
    the deleted_at column does not yet exist (Phase 2). The filter is wrapped in a
    column-existence check so it does not error on the current schema.

    Args:
        tenant_id: Tenant ID for isolation
        scope_artifact_id: UUID of the scope anchor artifact

    Returns:
        Set of descendant UUIDs (including anchor), or None if anchor not found
    """
    async with get_connection() as conn:
        # First verify the scope anchor exists, belongs to this tenant, and is not soft-deleted
        check_result = await conn.execute(
            f"""
            SELECT id FROM {SCHEMA_NAME}.artifact
            WHERE id = %s AND tenant_id = %s AND deleted_at IS NULL
            """,
            (str(scope_artifact_id), tenant_id),
        )
        anchor_row = await check_result.fetchone()
        if not anchor_row:
            return None

        # Recursive CTE to get all descendants
        # tenant_id and deleted_at IS NULL enforced at every level
        result = await conn.execute(
            f"""
            WITH RECURSIVE descendants AS (
                -- Base case: the scope anchor itself
                SELECT id
                FROM {SCHEMA_NAME}.artifact
                WHERE id = %s AND tenant_id = %s AND deleted_at IS NULL

                UNION ALL

                -- Recursive case: children of current level
                SELECT a.id
                FROM {SCHEMA_NAME}.artifact a
                INNER JOIN descendants d ON a.parent_artifact_id = d.id
                WHERE a.tenant_id = %s AND a.deleted_at IS NULL
            )
            SELECT id FROM descendants
            """,
            (str(scope_artifact_id), tenant_id, tenant_id),
        )
        rows = await result.fetchall()

    return {UUID(row[0]) if isinstance(row[0], str) else row[0] for row in rows}


def _build_scope_filter(descendant_ids: set[UUID], params: list, alias: str = "") -> str:
    """Build SQL WHERE clause fragment to restrict results to a set of artifact IDs.

    Args:
        descendant_ids: Set of artifact UUIDs from scope resolution
        params: mutable list of query parameters (appended to)
        alias: Table alias prefix (e.g., "a." for "a.id")

    Returns:
        SQL fragment like "AND a.id IN (%s, %s, %s)"
    """
    if not descendant_ids:
        # Empty set means scope resolved but no descendants found — return impossible condition
        return f" AND {alias}id IS NULL"

    placeholders = ",".join(["%s"] * len(descendant_ids))
    id_prefix = f"{alias}id" if alias else "id"
    params.extend(str(uid) for uid in descendant_ids)
    return f" AND {id_prefix} IN ({placeholders})"


# =============================================================================
# Search Functions
# =============================================================================


async def fulltext_search(
    tenant_id: int,
    query: str,
    artifact_types: list[str] | None = None,
    limit: int = 20,
    offset: int = 0,
    metadata_filters: dict[str, str | list[str]] | None = None,
    scope_artifact_id: UUID | None = None,
) -> SearchResponse:
    """Full-text search using PostgreSQL FTS."""
    # Resolve scope if provided
    scope_ids: set[UUID] | None = None
    if scope_artifact_id:
        scope_ids = await _resolve_scope_descendants(tenant_id, scope_artifact_id)
        if scope_ids is None:
            # Scope anchor not found — return empty
            return SearchResponse(results=[], total=0, query=query)

    async with get_connection() as conn:
        where_clause = "WHERE tenant_id = %s AND deleted_at IS NULL AND search_vector @@ plainto_tsquery('english', %s)"
        params: list = [tenant_id, query]

        if artifact_types:
            placeholders = ",".join(["%s"] * len(artifact_types))
            where_clause += f" AND artifact_type IN ({placeholders})"
            params.extend(artifact_types)

        # Metadata filter
        if metadata_filters:
            where_clause += _build_metadata_filter(metadata_filters, params)

        # Scope filter
        if scope_ids is not None:
            where_clause += _build_scope_filter(scope_ids, params)

        # Get count
        count_result = await conn.execute(
            f"SELECT COUNT(*) FROM {SCHEMA_NAME}.artifact {where_clause}",
            params,
        )
        total = (await count_result.fetchone())[0]

        # Get results with ranking
        # Build fresh params for select query: ts_rank param + WHERE params + LIMIT/OFFSET
        select_params: list = [query] + list(params) + [limit, offset]

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
            select_params,
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
    offset: int = 0,
    similarity_threshold: float = 0.0,
    metadata_filters: dict[str, str | list[str]] | None = None,
    scope_artifact_id: UUID | None = None,
) -> SearchResponse:
    """Semantic search using vector similarity.

    V2.2: Now supports offset, metadata_filters, scope_artifact_id.
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

    # Resolve scope if provided
    scope_ids: set[UUID] | None = None
    if scope_artifact_id:
        scope_ids = await _resolve_scope_descendants(tenant_id, scope_artifact_id)
        if scope_ids is None:
            return SearchResponse(results=[], total=0, query="(semantic)")

    vector_str = "[" + ",".join(str(v) for v in query_vector) + "]"

    async with get_connection() as conn:
        # Join embedding master table with vector child table and artifact
        where_clause = "WHERE e.tenant_id = %s AND a.deleted_at IS NULL"
        params: list = [tenant_id]

        if artifact_types:
            placeholders = ",".join(["%s"] * len(artifact_types))
            where_clause += f" AND a.artifact_type IN ({placeholders})"
            params.extend(artifact_types)

        # Metadata filter (on artifact table, aliased as "a")
        if metadata_filters:
            where_clause += _build_metadata_filter(metadata_filters, params).replace(
                "metadata @>", "a.metadata @>"
            )

        # Scope filter (on artifact table, aliased as "a")
        if scope_ids is not None:
            where_clause += _build_scope_filter(scope_ids, params, alias="a.")

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
            [vector_str] + params,
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

    # Total before pagination
    total = len(results)

    # Apply offset and limit
    results = results[offset : offset + limit]

    # Assign ranks (relative to offset)
    for i, result in enumerate(results):
        result.rank = offset + i + 1

    return SearchResponse(results=results, total=total, query="(semantic)")


async def hybrid_search(
    tenant_id: int,
    query: str,
    query_vector: list[float],
    embedding_type: str,
    artifact_types: list[str] | None = None,
    limit: int = 20,
    offset: int = 0,
    rrf_k: int = 60,
    semantic_weight: float = 0.5,
    metadata_filters: dict[str, str | list[str]] | None = None,
    scope_artifact_id: UUID | None = None,
) -> SearchResponse:
    """Hybrid search using Reciprocal Rank Fusion (RRF).

    V2.2: Now supports offset (applied after RRF merge), metadata_filters, scope_artifact_id.
    V2.1: Now requires embedding_type for the semantic search component.
    """
    # Get fulltext results (pass filters through; no offset — RRF needs full ranked lists)
    fts_response = await fulltext_search(
        tenant_id=tenant_id,
        query=query,
        artifact_types=artifact_types,
        limit=limit * 2,  # Fetch more for RRF
        offset=0,
        metadata_filters=metadata_filters,
        scope_artifact_id=scope_artifact_id,
    )

    # Get semantic results (pass filters through; no offset — RRF needs full ranked lists)
    sem_response = await semantic_search(
        tenant_id=tenant_id,
        query_vector=query_vector,
        embedding_type=embedding_type,
        artifact_types=artifact_types,
        limit=limit * 2,
        offset=0,
        metadata_filters=metadata_filters,
        scope_artifact_id=scope_artifact_id,
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

    # Total before pagination
    total = len(rrf_scores)

    # Apply offset and limit
    page = rrf_scores[offset : offset + limit]

    # Build results
    results = []
    for i, (artifact, score) in enumerate(page):
        results.append(SearchResult(artifact=artifact, score=score, rank=offset + i + 1))

    return SearchResponse(results=results, total=total, query=query)


async def similar_artifacts(
    tenant_id: int,
    artifact_id: UUID,
    embedding_type: str,
    limit: int = 10,
    offset: int = 0,
    artifact_types: list[str] | None = None,
    metadata_filters: dict[str, str | list[str]] | None = None,
    scope_artifact_id: UUID | None = None,
) -> SearchResponse:
    """Find artifacts similar to a given artifact using its embedding.

    V2.2: Now supports offset, metadata_filters, scope_artifact_id.
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

    # Find similar, excluding the source artifact (fetch extra to account for self-exclusion)
    response = await semantic_search(
        tenant_id=tenant_id,
        query_vector=query_vector,
        embedding_type=embedding_type,
        artifact_types=artifact_types,
        limit=limit + offset + 1,  # +1 to account for excluding self
        offset=0,
        metadata_filters=metadata_filters,
        scope_artifact_id=scope_artifact_id,
    )

    # Filter out the source artifact, then apply offset/limit
    all_results = [r for r in response.results if r.artifact.id != artifact_id]
    paged = all_results[offset : offset + limit]

    # Re-rank relative to offset
    for i, result in enumerate(paged):
        result.rank = offset + i + 1

    return SearchResponse(
        results=paged,
        total=len(all_results),
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