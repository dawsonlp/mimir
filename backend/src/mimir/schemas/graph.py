"""Schemas and exceptions for the Graph Traversal Engine.

These are the domain types returned by the graph engine. They are independent
of the context service schemas — the context service maps these into its own
ContextArtifact / RelationPathItem types for API responses.
"""

from dataclasses import dataclass, field
from uuid import UUID

# =============================================================================
# Domain Types
# =============================================================================


@dataclass(frozen=True, slots=True)
class PathStep:
    """A single edge traversal in a graph path.

    Captures the relation type, direction of traversal, and the two
    artifact endpoints of the edge.
    """

    relation_type: str
    direction: str  # "outgoing" or "incoming"
    from_artifact_id: UUID
    to_artifact_id: UUID


@dataclass(frozen=True, slots=True)
class TraversalResult:
    """One artifact discovered during graph traversal.

    Contains the artifact's UUID, its hop distance from the start vertex,
    and the full relation path taken to reach it (D3 requirement: full
    path data for argument chain validation).
    """

    artifact_id: UUID
    depth: int
    relation_path: list[PathStep] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class PathResult:
    """A single path between two specified artifacts.

    Returned by find_paths(), sorted shortest-first.
    """

    steps: list[PathStep]
    length: int
    start_artifact_id: UUID
    end_artifact_id: UUID


# =============================================================================
# Exceptions
# =============================================================================


class GraphScopeTooLargeError(Exception):
    """Raised when a traversal result set exceeds graph_max_result_set.

    The caller should map this to HTTP 422.
    """

    def __init__(self, count: int, limit: int) -> None:
        self.count = count
        self.limit = limit
        super().__init__(
            f"Graph traversal returned {count} vertices, exceeding the "
            f"maximum result set size of {limit}."
        )


class GraphQueryTimeoutError(Exception):
    """Raised when a Cypher query exceeds the configured statement_timeout.

    The caller should map this to HTTP 504.
    """

    def __init__(self, timeout_seconds: int) -> None:
        self.timeout_seconds = timeout_seconds
        super().__init__(f"Graph query exceeded the {timeout_seconds}s timeout.")


class GraphNotFoundError(Exception):
    """Raised when the tenant's AGE graph does not exist.

    This typically means migration 007 has not been applied for this tenant,
    or the tenant_id is invalid. The caller should map this to HTTP 404.
    """

    def __init__(self, graph_name: str) -> None:
        self.graph_name = graph_name
        super().__init__(
            f"Graph '{graph_name}' not found. Ensure the tenant exists "
            f"and AGE graph projection migration has been applied."
        )
