"""Context Retrieval Service - policy-driven context assembly for RAG applications.

This service is a separate domain concern from artifact/relation storage.
It provides policy-driven context assembly that determines what "relevant"
means for a given artifact.

Architectural Principles:
- Isolated: Own module, not embedded in artifact_service
- Policy-driven: Configurable rules for context assembly
- Extensible: Support future context strategies without API changes

Graph Traversal:
- Delegates to graph_engine.traverse() which uses Cypher VLP queries via AGE
- Previous Python-side BFS replaced in Phase 1F of graph engine implementation
"""

from datetime import UTC, datetime, timedelta
from uuid import UUID

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
    TemporalHint,
    TemporalMode,
)
from mimir.services import artifact_service, graph_engine

SCHEMA_NAME = "mimirdata"

# Policy configurations - defines which relations to follow and directions
# This could be moved to database or YAML for runtime configurability
POLICY_CONFIG: dict[ContextPolicy, dict] = {
    ContextPolicy.DIRECT_RELATIONS: {
        "description": "Include artifacts directly connected by any relation",
        "relation_types": None,  # None means all types
        "direction": "both",
        "max_depth": 1,  # Override: always 1 for direct
    },
    ContextPolicy.DERIVED_LINEAGE: {
        "description": "Include source and all derived artifacts",
        "relation_types": ["derived_from"],
        "direction": "both",
        "max_depth": None,  # Use requested depth
    },
    ContextPolicy.EVIDENCE_CHAIN: {
        "description": "Include supporting evidence chain",
        "relation_types": ["supports"],
        "direction": "both",
        "max_depth": None,
    },
    ContextPolicy.FULL_GRAPH: {
        "description": "All connected artifacts within N hops",
        "relation_types": None,  # All types
        "direction": "both",
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

    # Perform graph traversal via graph engine (replaces Python BFS)
    context_artifacts = await _traverse_graph(
        tenant_id=tenant_id,
        start_id=artifact_id,
        relation_types=config["relation_types"],
        direction=config["direction"],
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
    direction: str,
    max_depth: int,
    artifact_types: list[str] | None,
    exclusions: set[UUID],
) -> list[ContextArtifact]:
    """Traverse the artifact graph using the graph engine (Cypher VLP).

    Delegates to graph_engine.traverse(), then maps TraversalResult objects
    to ContextArtifact objects by batch-fetching artifact data.

    Returns context artifacts with their relation paths and distances.
    """
    # Call graph engine — this executes a single Cypher VLP query
    traversal_results = await graph_engine.traverse(
        tenant_id=tenant_id,
        start_artifact_id=start_id,
        max_depth=max_depth,
        relation_types=relation_types,
        direction=direction,
        include_start=False,  # Context service excludes the primary artifact
    )

    if not traversal_results:
        return []

    # Filter out excluded artifacts
    if exclusions:
        traversal_results = [
            r for r in traversal_results if r.artifact_id not in exclusions
        ]

    if not traversal_results:
        return []

    # Batch fetch all discovered artifacts
    artifact_ids = [r.artifact_id for r in traversal_results]
    artifacts_response = await artifact_service.list_artifacts(
        tenant_id=tenant_id,
        ids=artifact_ids,
    )

    # Build lookup for fetched artifacts
    artifacts_by_id = {a.id: a for a in artifacts_response.items}

    # Build context artifacts, filtering by type if requested
    context_artifacts: list[ContextArtifact] = []
    for result in traversal_results:
        artifact = artifacts_by_id.get(result.artifact_id)
        if not artifact:
            continue  # Artifact not found (defensive)

        # Filter by artifact type if specified
        if artifact_types and artifact.artifact_type not in artifact_types:
            continue

        # Map graph engine PathStep to context RelationPathItem
        relation_path = [
            RelationPathItem(
                relation_type=step.relation_type,
                direction=RelationDirection(step.direction),
            )
            for step in result.relation_path
        ]

        # Determine inclusion reason
        reason = _get_inclusion_reason(result)

        context_artifacts.append(
            ContextArtifact(
                artifact=artifact,
                relation_path=relation_path,
                distance=result.depth,
                relevance_score=None,
                inclusion_reason=reason,
            )
        )

    # Sort by distance, then by created_at for stability
    context_artifacts.sort(key=lambda ca: (ca.distance, ca.artifact.created_at))

    return context_artifacts


def _get_inclusion_reason(result) -> str:
    """Generate human-readable inclusion reason from TraversalResult."""
    if not result.relation_path:
        return f"Reached at depth {result.depth}"

    last_step = result.relation_path[-1]
    if result.depth == 1:
        if last_step.direction == "outgoing":
            return f"Direct {last_step.relation_type} from primary artifact"
        else:
            return f"Primary artifact is {last_step.relation_type} target"
    else:
        if last_step.direction == "outgoing":
            return f"Reached via {last_step.relation_type} (depth {result.depth})"
        else:
            return (
                f"Reached via incoming {last_step.relation_type} (depth {result.depth})"
            )


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

    # 3. Relevance threshold
    if hints.relevance_threshold is not None and hints.query:
        applied.relevance_filtering_applied = True
        # Future: filter by relevance_score >= threshold

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
    temporal: TemporalHint,
) -> list[ContextArtifact]:
    """Filter artifacts by temporal hint."""

    now = datetime.now(UTC)

    if temporal.mode == TemporalMode.RECENT:
        if temporal.days_back:
            cutoff = now - timedelta(days=temporal.days_back)
            return [ca for ca in artifacts if ca.artifact.created_at >= cutoff]

    elif temporal.mode == TemporalMode.HISTORICAL:
        if temporal.days_back:
            cutoff = now - timedelta(days=temporal.days_back)
            return [ca for ca in artifacts if ca.artifact.created_at < cutoff]

    elif temporal.mode == TemporalMode.RANGE:
        filtered = artifacts
        if temporal.start_date:
            start = datetime.combine(
                temporal.start_date, datetime.min.time(), tzinfo=UTC
            )
            filtered = [ca for ca in filtered if ca.artifact.created_at >= start]
        if temporal.end_date:
            end = datetime.combine(temporal.end_date, datetime.max.time(), tzinfo=UTC)
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
