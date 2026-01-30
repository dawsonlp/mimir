"""Context Retrieval Service - policy-driven context assembly for RAG applications.

This service is a separate domain concern from artifact/relation storage.
It provides policy-driven context assembly that determines what "relevant"
means for a given artifact.

Architectural Principles:
- Isolated: Own module, not embedded in artifact_service
- Policy-driven: Configurable rules for context assembly
- Extensible: Support future context strategies without API changes

Graph Traversal:
- Uses iterative approach (not recursive SQL)
- Tracks visited nodes to prevent cycles
- Respects depth limits strictly
"""

from datetime import datetime, timedelta, timezone
from uuid import UUID

from mimir.database import get_connection
from mimir.schemas.artifact import ArtifactResponse
from mimir.schemas.context import (
    ContextArtifact,
    ContextHints,
    ContextHintsApplied,
    ContextMetadata,
    ContextPolicy,
    ContextResponse,
    RelationDirection,
    RelationPathItem,
    TemporalMode,
)
from mimir.services import artifact_service

SCHEMA_NAME = "mimirdata"

# Policy configurations - defines which relations to follow and directions
# This could be moved to database or YAML for runtime configurability
POLICY_CONFIG: dict[ContextPolicy, dict] = {
    ContextPolicy.DIRECT_RELATIONS: {
        "description": "Include artifacts directly connected by any relation",
        "relation_types": None,  # None means all types
        "directions": ["outgoing", "incoming"],
        "max_depth": 1,  # Override: always 1 for direct
    },
    ContextPolicy.DERIVED_LINEAGE: {
        "description": "Include source and all derived artifacts",
        "relation_types": ["derived_from"],
        "directions": ["outgoing", "incoming"],
        "max_depth": None,  # Use requested depth
    },
    ContextPolicy.EVIDENCE_CHAIN: {
        "description": "Include supporting evidence chain",
        "relation_types": ["supports"],
        "directions": ["outgoing", "incoming"],
        "max_depth": None,
    },
    ContextPolicy.FULL_GRAPH: {
        "description": "All connected artifacts within N hops",
        "relation_types": None,  # All types
        "directions": ["outgoing", "incoming"],
        "max_depth": None,
    },
}


async def get_context(
    tenant_id: int,
    artifact_id: UUID,
    policy: ContextPolicy = ContextPolicy.DERIVED_LINEAGE,
    depth: int = 1,
    types: list[str] | None = None,
    include_content: bool = True,
    hints: ContextHints | None = None,
) -> ContextResponse | None:
    """Retrieve an artifact with its context according to the specified policy.
    
    Args:
        tenant_id: Tenant for isolation
        artifact_id: Primary artifact UUID
        policy: Context assembly policy
        depth: Maximum traversal depth
        types: Filter context artifacts by artifact_type
        include_content: Include artifact content in response
        hints: Optional hints to influence context assembly
        
    Returns:
        ContextResponse with primary artifact and context, or None if not found
    """
    # Fetch primary artifact
    primary = await artifact_service.get_artifact(artifact_id, tenant_id)
    if not primary:
        return None
    
    # Get policy configuration
    config = POLICY_CONFIG[policy]
    effective_depth = config["max_depth"] if config["max_depth"] is not None else depth
    
    # Build exclusions set from hints
    exclusions: set[UUID] = set()
    if hints and hints.exclusions:
        exclusions = set(hints.exclusions)
    
    # Perform graph traversal
    context_artifacts = await _traverse_graph(
        tenant_id=tenant_id,
        start_id=artifact_id,
        relation_types=config["relation_types"],
        directions=config["directions"],
        max_depth=effective_depth,
        artifact_types=types,
        exclusions=exclusions,
    )
    
    # Apply hints pipeline (if hints provided)
    hints_applied = ContextHintsApplied()
    artifacts_excluded = 0
    
    if hints:
        context_artifacts, hints_applied, artifacts_excluded = await _apply_hints(
            context_artifacts=context_artifacts,
            hints=hints,
            tenant_id=tenant_id,
        )
    
    # Optionally strip content
    if not include_content:
        primary = _strip_content(primary)
        context_artifacts = [
            ContextArtifact(
                artifact=_strip_content(ca.artifact),
                relation_path=ca.relation_path,
                distance=ca.distance,
                relevance_score=ca.relevance_score,
                inclusion_reason=ca.inclusion_reason,
            )
            for ca in context_artifacts
        ]
    
    return ContextResponse(
        artifact=primary,
        context=context_artifacts,
        policy=policy,
        hints_applied=hints_applied,
        metadata=ContextMetadata(
            depth_used=effective_depth,
            artifact_count=len(context_artifacts),
            tokens_estimated=None,  # Future: implement token estimation
            artifacts_excluded=artifacts_excluded,
        ),
    )


async def _traverse_graph(
    tenant_id: int,
    start_id: UUID,
    relation_types: list[str] | None,
    directions: list[str],
    max_depth: int,
    artifact_types: list[str] | None,
    exclusions: set[UUID],
) -> list[ContextArtifact]:
    """Iterative BFS graph traversal from start artifact.
    
    Tracks visited nodes to prevent cycles.
    Returns context artifacts with their relation paths.
    """
    visited: set[UUID] = {start_id}
    visited.update(exclusions)  # Pre-mark exclusions as visited
    
    # Queue: (artifact_id, path, distance)
    queue: list[tuple[UUID, list[RelationPathItem], int]] = [(start_id, [], 0)]
    results: list[tuple[UUID, list[RelationPathItem], int, str]] = []
    
    while queue:
        current_id, current_path, current_depth = queue.pop(0)
        
        # Don't traverse beyond max depth
        if current_depth >= max_depth:
            continue
        
        # Get relations from current node
        relations = await _get_relations_for_traversal(
            tenant_id=tenant_id,
            artifact_id=current_id,
            relation_types=relation_types,
            directions=directions,
        )
        
        for rel_type, target_id, direction in relations:
            if target_id in visited:
                continue
            
            visited.add(target_id)
            
            # Build path to this artifact
            new_path = current_path + [
                RelationPathItem(
                    relation_type=rel_type,
                    direction=RelationDirection(direction),
                )
            ]
            new_depth = current_depth + 1
            
            # Determine inclusion reason
            reason = _get_inclusion_reason(rel_type, direction, new_depth)
            
            results.append((target_id, new_path, new_depth, reason))
            
            # Continue traversal from this node
            queue.append((target_id, new_path, new_depth))
    
    if not results:
        return []
    
    # Batch fetch all discovered artifacts
    artifact_ids = [r[0] for r in results]
    artifacts_response = await artifact_service.list_artifacts(
        tenant_id=tenant_id,
        ids=artifact_ids,
    )
    
    # Build lookup for fetched artifacts
    artifacts_by_id = {a.id: a for a in artifacts_response.items}
    
    # Build context artifacts, filtering by type if requested
    context_artifacts: list[ContextArtifact] = []
    for artifact_id, path, distance, reason in results:
        artifact = artifacts_by_id.get(artifact_id)
        if not artifact:
            continue  # Artifact not found (shouldn't happen, but defensive)
        
        # Filter by artifact type if specified
        if artifact_types and artifact.artifact_type not in artifact_types:
            continue
        
        context_artifacts.append(
            ContextArtifact(
                artifact=artifact,
                relation_path=path,
                distance=distance,
                relevance_score=None,
                inclusion_reason=reason,
            )
        )
    
    # Sort by distance, then by created_at for stability
    context_artifacts.sort(key=lambda ca: (ca.distance, ca.artifact.created_at))
    
    return context_artifacts


async def _get_relations_for_traversal(
    tenant_id: int,
    artifact_id: UUID,
    relation_types: list[str] | None,
    directions: list[str],
) -> list[tuple[str, UUID, str]]:
    """Get relations from an artifact for traversal.
    
    Returns list of (relation_type, target_artifact_id, direction).
    """
    results: list[tuple[str, UUID, str]] = []
    
    async with get_connection() as conn:
        # Build query parts based on directions
        queries = []
        
        if "outgoing" in directions:
            # Artifact is source, follow to target
            where = "source_id = %s AND tenant_id = %s"
            params: list = [str(artifact_id), tenant_id]
            if relation_types:
                where += " AND relation_type = ANY(%s)"
                params.append(relation_types)
            
            queries.append((
                f"""
                SELECT relation_type, target_id, 'outgoing' as direction
                FROM {SCHEMA_NAME}.relation
                WHERE {where}
                """,
                params,
            ))
        
        if "incoming" in directions:
            # Artifact is target, follow back to source
            where = "target_id = %s AND tenant_id = %s"
            params = [str(artifact_id), tenant_id]
            if relation_types:
                where += " AND relation_type = ANY(%s)"
                params.append(relation_types)
            
            queries.append((
                f"""
                SELECT relation_type, source_id, 'incoming' as direction
                FROM {SCHEMA_NAME}.relation
                WHERE {where}
                """,
                params,
            ))
        
        for query, params in queries:
            result = await conn.execute(query, params)
            rows = await result.fetchall()
            for row in rows:
                rel_type = row[0]
                target = UUID(row[1]) if isinstance(row[1], str) else row[1]
                direction = row[2]
                results.append((rel_type, target, direction))
    
    return results


def _get_inclusion_reason(relation_type: str, direction: str, depth: int) -> str:
    """Generate human-readable inclusion reason."""
    if depth == 1:
        if direction == "outgoing":
            return f"Direct {relation_type} from primary artifact"
        else:
            return f"Primary artifact is {relation_type} target"
    else:
        if direction == "outgoing":
            return f"Reached via {relation_type} (depth {depth})"
        else:
            return f"Reached via incoming {relation_type} (depth {depth})"


async def _apply_hints(
    context_artifacts: list[ContextArtifact],
    hints: ContextHints,
    tenant_id: int,
) -> tuple[list[ContextArtifact], ContextHintsApplied, int]:
    """Apply hints pipeline to filter/transform context artifacts.
    
    Pipeline order:
    1. Exclusions (already handled in traversal)
    2. Temporal filtering
    3. Type preferences (affects scoring)
    4. Relevance scoring (if query provided)
    5. Token budget (truncate lowest-scored)
    """
    applied = ContextHintsApplied()
    excluded_count = 0
    result = context_artifacts.copy()
    
    # Track exclusions applied
    if hints.exclusions:
        applied.exclusions_applied = len(hints.exclusions)
    
    # 1. Temporal filtering
    if hints.temporal_focus:
        applied.temporal_filter_applied = True
        before_count = len(result)
        result = _apply_temporal_filter(result, hints.temporal_focus)
        excluded_count += before_count - len(result)
    
    # 2. Query provided (enables relevance scoring placeholder)
    if hints.query:
        applied.query_provided = True
        # Future: compute semantic similarity using embeddings
        # For now, this is a placeholder that could be extended
    
    # 3. Relevance threshold
    if hints.relevance_threshold is not None and hints.query:
        applied.relevance_filtering_applied = True
        # Future: filter by relevance_score >= threshold
        # Requires embedding-based scoring implementation
    
    # 4. Token budget (simple truncation for now)
    if hints.token_budget:
        applied.token_budget_enforced = True
        # Simple heuristic: limit number of artifacts based on budget
        # Rough estimate: ~500 tokens per artifact average
        max_artifacts = hints.token_budget // 500
        if len(result) > max_artifacts:
            excluded_count += len(result) - max_artifacts
            result = result[:max_artifacts]
    
    return result, applied, excluded_count


def _apply_temporal_filter(
    artifacts: list[ContextArtifact],
    temporal: "TemporalHint",
) -> list[ContextArtifact]:
    """Filter artifacts by temporal hint."""
    from mimir.schemas.context import TemporalMode
    
    now = datetime.now(timezone.utc)
    
    if temporal.mode == TemporalMode.RECENT:
        if temporal.days_back:
            cutoff = now - timedelta(days=temporal.days_back)
            return [
                ca for ca in artifacts
                if ca.artifact.created_at >= cutoff
            ]
    
    elif temporal.mode == TemporalMode.HISTORICAL:
        if temporal.days_back:
            cutoff = now - timedelta(days=temporal.days_back)
            return [
                ca for ca in artifacts
                if ca.artifact.created_at < cutoff
            ]
    
    elif temporal.mode == TemporalMode.RANGE:
        filtered = artifacts
        if temporal.start_date:
            start = datetime.combine(temporal.start_date, datetime.min.time(), tzinfo=timezone.utc)
            filtered = [ca for ca in filtered if ca.artifact.created_at >= start]
        if temporal.end_date:
            end = datetime.combine(temporal.end_date, datetime.max.time(), tzinfo=timezone.utc)
            filtered = [ca for ca in filtered if ca.artifact.created_at <= end]
        return filtered
    
    return artifacts


def _strip_content(artifact: ArtifactResponse) -> ArtifactResponse:
    """Create a copy of artifact with content stripped."""
    return ArtifactResponse(
        id=artifact.id,
        tenant_id=artifact.tenant_id,
        artifact_type=artifact.artifact_type,
        parent_artifact_id=artifact.parent_artifact_id,
        start_offset=artifact.start_offset,
        end_offset=artifact.end_offset,
        position_metadata=artifact.position_metadata,
        title=artifact.title,
        content=None,  # Strip content
        content_hash=artifact.content_hash,
        source=artifact.source,
        source_system=artifact.source_system,
        external_id=artifact.external_id,
        metadata=artifact.metadata,
        created_at=artifact.created_at,
    )