"""Intent and Intent Group API endpoints."""

from fastapi import APIRouter, Header, HTTPException, Query

from mimir.schemas.intent import (
    IntentCreate,
    IntentGroupCreate,
    IntentGroupListResponse,
    IntentGroupResponse,
    IntentGroupUpdate,
    IntentListResponse,
    IntentResponse,
    IntentUpdate,
)
from mimir.services import intent_service

router = APIRouter(tags=["intents"])


# ============================================================================
# Intent Group Endpoints
# ============================================================================


@router.post("/intent-groups", response_model=IntentGroupResponse, status_code=201)
async def create_intent_group(
    data: IntentGroupCreate,
    x_tenant_id: int = Header(..., description="Tenant ID"),
) -> IntentGroupResponse:
    """Create a new intent group."""
    return await intent_service.create_intent_group(x_tenant_id, data)


@router.get("/intent-groups", response_model=IntentGroupListResponse)
async def list_intent_groups(
    x_tenant_id: int = Header(..., description="Tenant ID"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> IntentGroupListResponse:
    """List intent groups for the tenant with pagination."""
    return await intent_service.list_intent_groups(x_tenant_id, page, page_size)


@router.get("/intent-groups/{group_id}", response_model=IntentGroupResponse)
async def get_intent_group(
    group_id: int,
    x_tenant_id: int = Header(..., description="Tenant ID"),
) -> IntentGroupResponse:
    """Get intent group by ID."""
    result = await intent_service.get_intent_group(group_id, x_tenant_id)
    if not result:
        raise HTTPException(status_code=404, detail="Intent group not found")
    return result


@router.patch("/intent-groups/{group_id}", response_model=IntentGroupResponse)
async def update_intent_group(
    group_id: int,
    data: IntentGroupUpdate,
    x_tenant_id: int = Header(..., description="Tenant ID"),
) -> IntentGroupResponse:
    """Update intent group."""
    result = await intent_service.update_intent_group(group_id, x_tenant_id, data)
    if not result:
        raise HTTPException(status_code=404, detail="Intent group not found")
    return result


@router.delete("/intent-groups/{group_id}", status_code=204)
async def delete_intent_group(
    group_id: int,
    x_tenant_id: int = Header(..., description="Tenant ID"),
) -> None:
    """Delete an intent group."""
    deleted = await intent_service.delete_intent_group(group_id, x_tenant_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Intent group not found")


# ============================================================================
# Intent Endpoints
# ============================================================================


@router.post("/intents", response_model=IntentResponse, status_code=201)
async def create_intent(
    data: IntentCreate,
    x_tenant_id: int = Header(..., description="Tenant ID"),
) -> IntentResponse:
    """Create a new intent."""
    return await intent_service.create_intent(x_tenant_id, data)


@router.get("/intents", response_model=IntentListResponse)
async def list_intents(
    x_tenant_id: int = Header(..., description="Tenant ID"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str | None = Query(None, description="Filter by status"),
    intent_group_id: int | None = Query(None, description="Filter by intent group"),
) -> IntentListResponse:
    """List intents for the tenant with pagination and filtering."""
    return await intent_service.list_intents(
        x_tenant_id, page, page_size, status, intent_group_id
    )


@router.get("/intents/{intent_id}", response_model=IntentResponse)
async def get_intent(
    intent_id: int,
    x_tenant_id: int = Header(..., description="Tenant ID"),
) -> IntentResponse:
    """Get intent by ID."""
    result = await intent_service.get_intent(intent_id, x_tenant_id)
    if not result:
        raise HTTPException(status_code=404, detail="Intent not found")
    return result


@router.patch("/intents/{intent_id}", response_model=IntentResponse)
async def update_intent(
    intent_id: int,
    data: IntentUpdate,
    x_tenant_id: int = Header(..., description="Tenant ID"),
) -> IntentResponse:
    """Update intent."""
    result = await intent_service.update_intent(intent_id, x_tenant_id, data)
    if not result:
        raise HTTPException(status_code=404, detail="Intent not found")
    return result


@router.delete("/intents/{intent_id}", status_code=204)
async def delete_intent(
    intent_id: int,
    x_tenant_id: int = Header(..., description="Tenant ID"),
) -> None:
    """Delete an intent."""
    deleted = await intent_service.delete_intent(intent_id, x_tenant_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Intent not found")
