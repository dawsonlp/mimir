"""Unit coverage for tenant metadata JSONB adaptation."""

from contextlib import asynccontextmanager
from datetime import UTC, datetime

import pytest

from mimir.schemas.tenant import TenantCreate, TenantResponse, TenantUpdate
from mimir.services import tenant_service

CREATED_AT = datetime(2026, 6, 4, 12, 0, 0, tzinfo=UTC)


class FakeResult:
    def __init__(self, row=None):
        self.row = row

    async def fetchone(self):
        return self.row


class FakeConnection:
    def __init__(self):
        self.executed = []
        self.commits = 0

    async def execute(self, sql, params=None):
        self.executed.append((sql, params))

        if "SELECT t.id" in sql:
            return FakeResult(
                (
                    1,
                    "larnet",
                    "Larnet",
                    "environment",
                    None,
                    True,
                    CREATED_AT,
                    {"source": "refresh"},
                )
            )

        return FakeResult()

    async def commit(self):
        self.commits += 1


@asynccontextmanager
async def fake_connection_context(conn):
    yield conn


@pytest.mark.asyncio
async def test_create_tenant_wraps_metadata_as_json(monkeypatch):
    conn = FakeConnection()
    monkeypatch.setattr(
        tenant_service, "get_connection", lambda: fake_connection_context(conn)
    )

    tenant = await tenant_service.create_tenant(
        TenantCreate(
            shortname="larnet",
            name="Larnet",
            metadata={"source": "refresh"},
        )
    )

    insert_params = conn.executed[0][1]
    assert insert_params[5].obj == {"source": "refresh"}
    assert tenant.metadata == {"source": "refresh"}
    assert conn.commits == 1


@pytest.mark.asyncio
async def test_create_tenant_preserves_empty_metadata_object(monkeypatch):
    conn = FakeConnection()
    monkeypatch.setattr(
        tenant_service, "get_connection", lambda: fake_connection_context(conn)
    )

    await tenant_service.create_tenant(
        TenantCreate(shortname="larnet", name="Larnet", metadata={})
    )

    insert_params = conn.executed[0][1]
    assert insert_params[5].obj == {}


@pytest.mark.asyncio
async def test_update_tenant_wraps_metadata_as_json(monkeypatch):
    conn = FakeConnection()

    async def fake_get_tenant(tenant_id):
        return TenantResponse(
            id=tenant_id,
            shortname="larnet",
            name="Larnet",
            tenant_type="environment",
            description=None,
            is_active=True,
            created_at=CREATED_AT,
            metadata={"source": "refresh"},
        )

    monkeypatch.setattr(
        tenant_service, "get_connection", lambda: fake_connection_context(conn)
    )
    monkeypatch.setattr(tenant_service, "get_tenant", fake_get_tenant)

    tenant = await tenant_service.update_tenant(
        1, TenantUpdate(metadata={"source": "refresh"})
    )

    update_params = conn.executed[0][1]
    assert update_params[0].obj == {"source": "refresh"}
    assert update_params[1] == 1
    assert tenant is not None
    assert tenant.metadata == {"source": "refresh"}
    assert conn.commits == 1
