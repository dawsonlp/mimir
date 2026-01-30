"""Provenance API endpoints (V2 append-only).

V2 Changes:
- UUID path parameters (not INT)
- No POST endpoint (events are auto-created)
- TEXT fields instead of enums
- Read-only from API perspective
"""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Query

from mimir.schemas.provenance import (
    ProvenanceEventListResponse,
    ProvenanceEventResponse,
)
from mimir.services import provenance_service

router = APIRouter(prefix="/provenance", tags=["provenance"])


@router.get("", response_model=ProvenanceEventListResponse)
async def list_provenance_events(
    x_tenant_id: int = Header(..., alias="X-Tenant-ID"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    entity_type: str | None = Query(None, description="Filter by entity type: artifact, relation, embedding"),
    entity_id: UUID | None = Query(None, description="Filter by entity UUID"),
    action: str | None = Query(None, description="Filter by action: create"),
    actor_type: str | None = Query(None, description="Filter by actor type: user, system, llm, api_client, migration"),
    actor_id: str | None = Query(None, description="Filter by actor ID"),
    after: datetime | None = Query(None, description="Filter events after this timestamp"),
    before: datetime | None = Query(None, description="Filter events before this timestamp"),
) -> ProvenanceEventListResponse:
    """List provenance events with optional filtering."""
    return await provenance_service.list_provenance_events(
        x_tenant_id, limit, offset, entity_type, entity_id, action, actor_type, actor_id, after, before
    )


@router.get("/artifact/{artifact_id}", response_model=list[ProvenanceEventResponse])
async def get_artifact_history(
    artifact_id: UUID,
    x_tenant_id: int = Header(..., alias="X-Tenant-ID"),
) -> list[ProvenanceEventResponse]:
    """Get full provenance history for a specific artifact."""
    return await provenance_service.get_artifact_history(x_tenant_id, artifact_id)


# NOTE: POST endpoint removed - provenance events are auto-created when artifacts/relations/embeddings are created
# NOTE: Entity type enum removed - using TEXT for flexibility
# NOTE: Action enum removed - only 'create' for now (append-only system)
