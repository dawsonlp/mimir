"""Decision API endpoints."""

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel

from mimir.schemas.decision import (
    DecisionCreate,
    DecisionListResponse,
    DecisionResponse,
    DecisionSupersede,
    DecisionUpdate,
)
from mimir.services import decision_service

router = APIRouter(prefix="/decisions", tags=["decisions"])


class SupersedeResponse(BaseModel):
    """Response for supersede operation."""

    old_decision: DecisionResponse
    new_decision: DecisionResponse


@router.post("", response_model=DecisionResponse, status_code=201)
async def create_decision(
    data: DecisionCreate,
    x_tenant_id: int = Header(..., description="Tenant ID"),
) -> DecisionResponse:
    """Create a new decision."""
    return await decision_service.create_decision(x_tenant_id, data)


@router.get("", response_model=DecisionListResponse)
async def list_decisions(
    x_tenant_id: int = Header(..., description="Tenant ID"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str | None = Query(None, description="Filter by status"),
    intent_id: int | None = Query(None, description="Filter by intent"),
    artifact_id: int | None = Query(None, description="Filter by artifact"),
) -> DecisionListResponse:
    """List decisions for the tenant with pagination and filtering."""
    return await decision_service.list_decisions(
        x_tenant_id, page, page_size, status, intent_id, artifact_id
    )


@router.get("/{decision_id}", response_model=DecisionResponse)
async def get_decision(
    decision_id: int,
    x_tenant_id: int = Header(..., description="Tenant ID"),
) -> DecisionResponse:
    """Get decision by ID."""
    result = await decision_service.get_decision(decision_id, x_tenant_id)
    if not result:
        raise HTTPException(status_code=404, detail="Decision not found")
    return result


@router.patch("/{decision_id}", response_model=DecisionResponse)
async def update_decision(
    decision_id: int,
    data: DecisionUpdate,
    x_tenant_id: int = Header(..., description="Tenant ID"),
) -> DecisionResponse:
    """Update decision."""
    result = await decision_service.update_decision(decision_id, x_tenant_id, data)
    if not result:
        raise HTTPException(status_code=404, detail="Decision not found")
    return result


@router.delete("/{decision_id}", status_code=204)
async def delete_decision(
    decision_id: int,
    x_tenant_id: int = Header(..., description="Tenant ID"),
) -> None:
    """Delete a decision."""
    deleted = await decision_service.delete_decision(decision_id, x_tenant_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Decision not found")


@router.post("/{decision_id}/supersede", response_model=SupersedeResponse, status_code=201)
async def supersede_decision(
    decision_id: int,
    data: DecisionSupersede,
    x_tenant_id: int = Header(..., description="Tenant ID"),
) -> SupersedeResponse:
    """Supersede a decision with a new one.

    Creates a new decision and marks the original as superseded.
    The new decision inherits artifact_id, intent_id, and source from the original.
    """
    result = await decision_service.supersede_decision(decision_id, x_tenant_id, data)
    if not result:
        raise HTTPException(status_code=404, detail="Decision not found")
    old_decision, new_decision = result
    return SupersedeResponse(old_decision=old_decision, new_decision=new_decision)
