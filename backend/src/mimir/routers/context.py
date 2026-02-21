"""Context Retrieval API endpoints.

Provides policy-driven context assembly for RAG applications.
Single request retrieves an artifact along with all contextually relevant artifacts.

This is a separate domain concern from artifact/relation storage.
All context assembly logic lives in the service layer.
"""

from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Query

from mimir.schemas.context import (
    ContextHints,
    ContextPolicy,
    ContextResponse,
)
from mimir.services import context_service

router = APIRouter(prefix="/context", tags=["context"])


def _parse_types(types_param: str | None) -> list[str] | None:
    """Parse comma-separated artifact types from query parameter."""
    if not types_param:
        return None

    types = [t.strip() for t in types_param.split(",") if t.strip()]
    return types if types else None


@router.post(
    "/{artifact_id}",
    response_model=ContextResponse,
    summary="Retrieve artifact with context",
    response_description="Primary artifact and contextually relevant artifacts",
)
async def get_context(
    artifact_id: UUID,
    x_tenant_id: int = Header(..., alias="X-Tenant-ID"),
    policy: ContextPolicy = Query(
        ContextPolicy.DERIVED_LINEAGE,
        description="Context assembly policy. "
        "direct_relations: directly connected artifacts. "
        "derived_lineage: follow derived_from chain. "
        "evidence_chain: follow supports chain. "
        "full_graph: all connected within N hops.",
    ),
    depth: int = Query(
        1,
        ge=1,
        le=10,
        description="Maximum traversal depth for graph policies",
    ),
    types: str | None = Query(
        None,
        description="Comma-separated artifact types to include in context",
    ),
    include_content: bool = Query(
        True,
        description="Include artifact content in response",
    ),
    hints: ContextHints | None = None,
) -> ContextResponse:
    """Retrieve an artifact with all contextually relevant artifacts.

    **Context Policies**:
    - `direct_relations`: Include artifacts directly connected by any relation
    - `derived_lineage`: Include source and all derived artifacts (follow derived_from chain)
    - `evidence_chain`: Include supporting evidence (follow supports chain)
    - `full_graph`: All connected artifacts within N hops

    **Request Body (optional)**: ContextHints

    Pass hints in the request body to influence context assembly:
    - `query`: Enable semantic relevance scoring
    - `token_budget`: Limit context size
    - `temporal_focus`: Filter by creation date
    - `exclusions`: Artifacts to exclude

    **Examples**:

    Basic context retrieval:
    ```
    POST /context/550e8400-e29b-41d4-a716-446655440000?policy=derived_lineage&depth=2
    ```

    With hints for Q&A:
    ```json
    {
      "query": "What are the security considerations?",
      "task_type": "qa",
      "token_budget": 4000
    }
    ```
    """
    parsed_types = _parse_types(types)

    result = await context_service.get_context(
        tenant_id=x_tenant_id,
        artifact_id=artifact_id,
        policy=policy,
        depth=depth,
        types=parsed_types,
        include_content=include_content,
        hints=hints,
    )

    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"Artifact {artifact_id} not found",
        )

    return result
