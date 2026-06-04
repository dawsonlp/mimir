"""Unit coverage for atomic create/provenance/outbox write paths."""

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from uuid import UUID

import pytest
from psycopg import errors as pg_errors

from mimir.schemas.artifact import ArtifactCreate
from mimir.services import artifact_service

ARTIFACT_ID = UUID("019e9052-aaaa-7000-9000-000000000001")
PROVENANCE_ID = UUID("019e9052-bbbb-7000-9000-000000000002")
OUTBOX_ID = UUID("019e9052-cccc-7000-9000-000000000003")
CREATED_AT = datetime(2026, 6, 4, 1, 49, 24, 535000, tzinfo=UTC)


class FakeResult:
    def __init__(self, row):
        self.row = row

    async def fetchone(self):
        return self.row


class FakeConnection:
    def __init__(self, *, fail_first_insert: bool = False):
        self.fail_first_insert = fail_first_insert
        self.executed = []
        self.commits = 0
        self.rollbacks = 0

    async def execute(self, sql, params=None):
        self.executed.append((sql, params))

        if self.fail_first_insert:
            raise pg_errors.UniqueViolation("duplicate artifact id")

        if "INSERT INTO mimirdata.artifact" in sql:
            return FakeResult(
                (
                    str(ARTIFACT_ID),
                    1,
                    "document",
                    None,
                    None,
                    None,
                    None,
                    "CR-1",
                    "full content must stay out of the change payload",
                    "abc123",
                    "manual",
                    "efforts",
                    "REQ-1",
                    {"priority": "high"},
                    CREATED_AT,
                )
            )

        if "INSERT INTO mimirdata.provenance_event" in sql:
            return FakeResult(
                (
                    str(PROVENANCE_ID),
                    1,
                    "artifact",
                    str(ARTIFACT_ID),
                    "create",
                    "api_client",
                    None,
                    None,
                    {"title": "CR-1", "artifact_type": "document"},
                    CREATED_AT,
                )
            )

        if "INSERT INTO mimirdata.change_outbox" in sql:
            payload = params[6].obj
            return FakeResult(
                (
                    str(OUTBOX_ID),
                    1,
                    42,
                    "artifact",
                    str(ARTIFACT_ID),
                    "create",
                    CREATED_AT,
                    str(PROVENANCE_ID),
                    None,
                    "api_client",
                    None,
                    payload,
                )
            )

        raise AssertionError(f"Unexpected SQL: {sql}")

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


@asynccontextmanager
async def fake_connection_context(conn):
    yield conn


@pytest.mark.asyncio
async def test_create_artifact_commits_domain_provenance_and_outbox_once(monkeypatch):
    conn = FakeConnection()
    monkeypatch.setattr(
        artifact_service, "get_connection", lambda: fake_connection_context(conn)
    )

    result = await artifact_service.create_artifact(
        1,
        ArtifactCreate(
            id=ARTIFACT_ID,
            artifact_type="document",
            title="CR-1",
            content="full content must stay out of the change payload",
            source="manual",
            source_system="efforts",
            external_id="REQ-1",
            metadata={"priority": "high"},
        ),
    )

    assert result is not None
    assert result.id == ARTIFACT_ID
    assert conn.commits == 1
    assert conn.rollbacks == 0

    statements = [sql for sql, _ in conn.executed]
    assert "INSERT INTO mimirdata.artifact" in statements[0]
    assert "INSERT INTO mimirdata.provenance_event" in statements[1]
    assert "INSERT INTO mimirdata.change_outbox" in statements[2]

    outbox_params = conn.executed[2][1]
    assert outbox_params[0] == 1
    assert outbox_params[1] == "artifact"
    assert outbox_params[2] == str(ARTIFACT_ID)
    assert outbox_params[3] == str(PROVENANCE_ID)
    assert outbox_params[4] == "api_client"
    assert outbox_params[6].obj == {
        "artifact_type": "document",
        "parent_artifact_id": None,
        "source": "manual",
        "source_system": "efforts",
        "external_id": "REQ-1",
        "content_hash": "abc123",
    }


@pytest.mark.asyncio
async def test_create_artifact_duplicate_rolls_back_before_outbox(monkeypatch):
    conn = FakeConnection(fail_first_insert=True)
    monkeypatch.setattr(
        artifact_service, "get_connection", lambda: fake_connection_context(conn)
    )

    result = await artifact_service.create_artifact(
        1, ArtifactCreate(id=ARTIFACT_ID, artifact_type="document")
    )

    assert result is None
    assert conn.commits == 0
    assert conn.rollbacks == 1
    assert len(conn.executed) == 1
