"""Graph Traversal Engine — Cypher-based graph traversal via Apache AGE.

Replaces the Python-side BFS in context_service with single-query Cypher
variable-length path (VLP) queries executed inside PostgreSQL/AGE.

Design decisions:
- D1: Acquires own connection via get_connection() (no conn parameter)
- D2: include_start=True by default for backward compat
- D3: Returns full path data (relation_path) for argument chain validation
- D6: Uses SET LOCAL statement_timeout for DB-side query timeout enforcement

AGE 1.7.0 capabilities (validated by spike):
- ✅ Variable-length paths (outgoing + undirected)
- ✅ length(path), nodes(path), relationships(path)
- ✅ LIMIT, ORDER BY length(path)
- ❌ ALL() predicate — relation type filtering done in Python
- ❌ shortestPath() — use VLP + ORDER BY length + LIMIT instead
"""

import logging
from uuid import UUID

import psycopg

from mimir.config import get_settings
from mimir.database import get_connection
from mimir.schemas.graph import (
    GraphNotFoundError,
    GraphQueryTimeoutError,
    GraphScopeTooLargeError,
    PathResult,
    PathStep,
    TraversalResult,
)
from mimir.services.agtype_parser import parse_agtype_collection

logger = logging.getLogger(__name__)


# =============================================================================
# Internal Helpers
# =============================================================================


async def _execute_cypher(
    graph_name: str,
    cypher: str,
    timeout_seconds: int | None = None,
) -> list[tuple]:
    """Execute a Cypher query against an AGE graph and return raw rows.

    Acquires its own connection from the pool (D1). Sets a per-transaction
    statement timeout (D6) to prevent runaway queries.

    Args:
        graph_name: The AGE graph name (e.g. ``mimir_tenant_1``).
        cypher: The Cypher query string.
        timeout_seconds: Override timeout; uses config default if None.

    Returns:
        List of row tuples from the query.

    Raises:
        GraphQueryTimeoutError: If the query exceeds the timeout.
        GraphNotFoundError: If the graph does not exist.
    """
    settings = get_settings()
    timeout = timeout_seconds or settings.graph_query_timeout_seconds

    async with get_connection() as conn:
        try:
            await conn.execute(
                f"SET LOCAL statement_timeout = '{timeout}s'"
            )
            result = await conn.execute(
                "SELECT * FROM ag_catalog.cypher(%s, %s) AS (result agtype)",
                [graph_name, cypher],
            )
            rows = await result.fetchall()
            return rows

        except psycopg.errors.QueryCanceled:
            raise GraphQueryTimeoutError(timeout)

        except psycopg.errors.InvalidParameterValue as exc:
            # AGE raises InvalidParameterValue when graph doesn't exist
            error_msg = str(exc).lower()
            if "graph" in error_msg and ("not" in error_msg or "does" in error_msg):
                raise GraphNotFoundError(graph_name) from exc
            raise

        except psycopg.errors.UndefinedTable as exc:
            # Alternative error when graph schema is missing
            raise GraphNotFoundError(graph_name) from exc


def _build_traverse_cypher(
    start_mimir_id: str,
    max_depth: int,
    direction: str = "both",
    limit: int = 500,
) -> str:
    """Build a Cypher VLP query for graph traversal.

    Pure function — parameters in, Cypher string out.

    Args:
        start_mimir_id: The mimir_id of the start artifact vertex.
        max_depth: Maximum path length (hops).
        direction: ``"outgoing"``, ``"incoming"``, or ``"both"`` (undirected).
        limit: Maximum number of paths to return.

    Returns:
        Cypher query string.
    """
    if direction == "outgoing":
        pattern = f"(start:Artifact {{mimir_id: '{start_mimir_id}'}})-[*1..{max_depth}]->(end:Artifact)"
    elif direction == "incoming":
        pattern = f"(start:Artifact {{mimir_id: '{start_mimir_id}'}})<-[*1..{max_depth}]-(end:Artifact)"
    else:
        # "both" — undirected
        pattern = f"(start:Artifact {{mimir_id: '{start_mimir_id}'}})-[*1..{max_depth}]-(end:Artifact)"

    return f"MATCH path = {pattern} RETURN path LIMIT {limit}"


def _build_find_paths_cypher(
    from_mimir_id: str,
    to_mimir_id: str,
    max_depth: int,
    limit: int = 10,
) -> str:
    """Build a Cypher VLP query for finding paths between two artifacts.

    Pure function. Returns paths shortest-first via ORDER BY length(path).

    Args:
        from_mimir_id: Start artifact mimir_id.
        to_mimir_id: End artifact mimir_id.
        max_depth: Maximum path length.
        limit: Maximum paths to return.

    Returns:
        Cypher query string.
    """
    return (
        f"MATCH path = (a:Artifact {{mimir_id: '{from_mimir_id}'}})"
        f"-[*1..{max_depth}]-"
        f"(b:Artifact {{mimir_id: '{to_mimir_id}'}}) "
        f"RETURN path "
        f"ORDER BY length(path) ASC "
        f"LIMIT {limit}"
    )


def _extract_path_steps(path_elements: list[dict], start_mimir_id: str) -> list[PathStep]:
    """Extract PathStep list from a parsed AGE path.

    A path from AGE is [vertex, edge, vertex, edge, vertex, ...].
    Vertices are at even indices, edges at odd indices.

    For each edge, we determine direction by comparing the edge's start_id
    with the preceding vertex's id. If the edge starts from the preceding
    vertex, direction is "outgoing"; otherwise "incoming".

    Args:
        path_elements: Parsed list of dicts from parse_agtype_collection().
        start_mimir_id: The mimir_id of the traversal start vertex.

    Returns:
        List of PathStep instances.
    """
    steps: list[PathStep] = []

    # Walk the path: vertex at i, edge at i+1, next vertex at i+2
    for i in range(0, len(path_elements) - 1, 2):
        if i + 1 >= len(path_elements):
            break

        current_vertex = path_elements[i]
        edge = path_elements[i + 1]
        next_vertex = path_elements[i + 2] if i + 2 < len(path_elements) else None

        if next_vertex is None:
            break

        # Determine direction based on edge start_id matching current vertex id
        current_id = current_vertex["id"]
        edge_start = edge.get("start_id")

        if edge_start == current_id:
            direction = "outgoing"
            from_mimir_id = current_vertex["properties"].get("mimir_id", "")
            to_mimir_id = next_vertex["properties"].get("mimir_id", "")
        else:
            direction = "incoming"
            from_mimir_id = next_vertex["properties"].get("mimir_id", "")
            to_mimir_id = current_vertex["properties"].get("mimir_id", "")

        relation_type = edge["properties"].get("relation_type", "unknown")

        steps.append(
            PathStep(
                relation_type=relation_type,
                direction=direction,
                from_artifact_id=UUID(from_mimir_id),
                to_artifact_id=UUID(to_mimir_id),
            )
        )

    return steps


def _filter_paths_by_relation_types(
    paths_with_elements: list[tuple[list[dict], list[PathStep]]],
    relation_types: list[str],
) -> list[tuple[list[dict], list[PathStep]]]:
    """Filter paths where ALL edges match the allowed relation types.

    AGE 1.7.0 lacks the ALL() predicate, so we filter in Python.

    Args:
        paths_with_elements: List of (raw_elements, path_steps) tuples.
        relation_types: Allowed relation type names.

    Returns:
        Filtered list containing only paths where every edge matches.
    """
    allowed = set(relation_types)
    return [
        (elements, steps)
        for elements, steps in paths_with_elements
        if all(step.relation_type in allowed for step in steps)
    ]


# =============================================================================
# Public API
# =============================================================================


async def traverse(
    tenant_id: int,
    start_artifact_id: UUID,
    max_depth: int | None = None,
    relation_types: list[str] | None = None,
    direction: str = "both",
    include_start: bool = True,
) -> list[TraversalResult]:
    """Traverse the artifact graph from a start vertex using Cypher VLP.

    Args:
        tenant_id: Tenant ID for graph isolation.
        start_artifact_id: UUID of the starting artifact.
        max_depth: Maximum traversal depth. Defaults to config graph_max_depth.
        relation_types: If specified, only paths where ALL edges match
            these types are included (Python-side filtering since AGE 1.7.0
            lacks ALL() predicate).
        direction: ``"outgoing"``, ``"incoming"``, or ``"both"``.
        include_start: If True, include the start artifact at depth 0 (D2).

    Returns:
        List of TraversalResult sorted by depth ascending.

    Raises:
        GraphScopeTooLargeError: If result set exceeds graph_max_result_set.
        GraphQueryTimeoutError: If query exceeds timeout.
        GraphNotFoundError: If tenant graph doesn't exist.
    """
    settings = get_settings()
    effective_depth = max_depth if max_depth is not None else settings.graph_max_depth
    graph_name = f"mimir_tenant_{tenant_id}"
    start_id_str = str(start_artifact_id)

    cypher = _build_traverse_cypher(
        start_mimir_id=start_id_str,
        max_depth=effective_depth,
        direction=direction,
        limit=settings.graph_max_result_set,
    )

    logger.debug("Executing traverse Cypher on %s: %s", graph_name, cypher)
    rows = await _execute_cypher(graph_name, cypher)

    # Parse paths and extract steps
    # Each row is a single-element tuple containing the path as agtype string
    seen_artifacts: dict[UUID, TraversalResult] = {}
    paths_with_elements: list[tuple[list[dict], list[PathStep]]] = []

    for row in rows:
        raw_path = row[0] if row else None
        if raw_path is None:
            continue

        path_elements = parse_agtype_collection(str(raw_path))
        if not path_elements:
            continue

        steps = _extract_path_steps(path_elements, start_id_str)
        paths_with_elements.append((path_elements, steps))

    # Apply relation type filter in Python (AGE 1.7.0 lacks ALL())
    if relation_types:
        paths_with_elements = _filter_paths_by_relation_types(
            paths_with_elements, relation_types
        )

    # Build TraversalResult for each unique end artifact, keeping shortest path
    for path_elements, steps in paths_with_elements:
        if not path_elements:
            continue

        # End artifact is the last vertex in the path
        end_vertex = path_elements[-1]
        end_mimir_id_str = end_vertex.get("properties", {}).get("mimir_id", "")
        if not end_mimir_id_str:
            continue

        try:
            end_artifact_id = UUID(end_mimir_id_str)
        except ValueError:
            logger.warning("Invalid UUID in vertex mimir_id: %s", end_mimir_id_str)
            continue

        depth = len(steps)

        # Keep shortest path to each artifact
        if end_artifact_id not in seen_artifacts or depth < seen_artifacts[end_artifact_id].depth:
            seen_artifacts[end_artifact_id] = TraversalResult(
                artifact_id=end_artifact_id,
                depth=depth,
                relation_path=steps,
            )

    results = list(seen_artifacts.values())

    # Include start artifact at depth 0 if requested (D2)
    if include_start:
        results.insert(
            0,
            TraversalResult(
                artifact_id=start_artifact_id,
                depth=0,
                relation_path=[],
            ),
        )

    # Enforce result set limit
    if len(results) > settings.graph_max_result_set:
        raise GraphScopeTooLargeError(len(results), settings.graph_max_result_set)

    # Sort by depth ascending, stable order
    results.sort(key=lambda r: r.depth)

    logger.debug(
        "Traverse from %s returned %d artifacts (depth 0-%d)",
        start_artifact_id,
        len(results),
        max(r.depth for r in results) if results else 0,
    )

    return results


async def find_paths(
    tenant_id: int,
    from_artifact_id: UUID,
    to_artifact_id: UUID,
    max_depth: int | None = None,
    limit: int = 10,
) -> list[PathResult]:
    """Find paths between two artifacts, returned shortest-first.

    Uses VLP + ORDER BY length(path) since AGE 1.7.0 lacks shortestPath().

    Args:
        tenant_id: Tenant ID for graph isolation.
        from_artifact_id: Start artifact UUID.
        to_artifact_id: End artifact UUID.
        max_depth: Maximum path length. Defaults to config graph_max_depth.
        limit: Maximum number of paths to return.

    Returns:
        List of PathResult, sorted by path length ascending.

    Raises:
        GraphQueryTimeoutError: If query exceeds timeout.
        GraphNotFoundError: If tenant graph doesn't exist.
    """
    settings = get_settings()
    effective_depth = max_depth if max_depth is not None else settings.graph_max_depth
    graph_name = f"mimir_tenant_{tenant_id}"

    cypher = _build_find_paths_cypher(
        from_mimir_id=str(from_artifact_id),
        to_mimir_id=str(to_artifact_id),
        max_depth=effective_depth,
        limit=limit,
    )

    logger.debug("Executing find_paths Cypher on %s: %s", graph_name, cypher)
    rows = await _execute_cypher(graph_name, cypher)

    results: list[PathResult] = []

    for row in rows:
        raw_path = row[0] if row else None
        if raw_path is None:
            continue

        path_elements = parse_agtype_collection(str(raw_path))
        if not path_elements:
            continue

        steps = _extract_path_steps(path_elements, str(from_artifact_id))
        if not steps:
            continue

        results.append(
            PathResult(
                steps=steps,
                length=len(steps),
                start_artifact_id=from_artifact_id,
                end_artifact_id=to_artifact_id,
            )
        )

    logger.debug(
        "find_paths %s → %s returned %d paths",
        from_artifact_id,
        to_artifact_id,
        len(results),
    )

    return results