"""Unit tests for the Mimir outbox publisher loop behavior."""

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from uuid import UUID

import pytest

from mimir.outbox_publisher import OutboxPublisherConfig, run_once
from mimir.schemas.change_outbox import ChangeOutboxEvent
from mimir.services.change_outbox import ChangeOutboxRow

EVENT_ID = UUID("019e9052-cccc-7000-9000-000000000003")
ENTITY_ID = UUID("019e9052-aaaa-7000-9000-000000000001")
OCCURRED_AT = datetime(2026, 6, 4, 1, 49, 24, 535000, tzinfo=UTC)


class FakeConnection:
    def __init__(self):
        self.commits = 0

    async def commit(self):
        self.commits += 1


class FakeProducer:
    def __init__(self, *, fail: bool = False):
        self.fail = fail
        self.published = []

    async def publish(self, *, topic, row):
        if self.fail:
            raise RuntimeError("broker unavailable")
        self.published.append((topic, row.event.event_id))


def _config() -> OutboxPublisherConfig:
    return OutboxPublisherConfig(
        kafka_bootstrap_servers="kafka:9092",
        topic="mimir.changes.v1",
        batch_size=100,
        poll_interval_seconds=1.0,
        retry_base_seconds=1,
        retry_max_seconds=300,
    )


def _row(publish_attempts: int = 0) -> ChangeOutboxRow:
    return ChangeOutboxRow(
        event=ChangeOutboxEvent(
            event_id=EVENT_ID,
            tenant_id=1,
            sequence=42,
            entity_type="artifact",
            entity_id=ENTITY_ID,
            occurred_at=OCCURRED_AT,
            payload={"artifact_type": "document"},
        ),
        publish_attempts=publish_attempts,
        last_error=None,
    )


@asynccontextmanager
async def fake_connection_context(conn):
    yield conn


@pytest.mark.asyncio
async def test_run_once_marks_acknowledged_rows_published(monkeypatch):
    conn = FakeConnection()
    marked = []

    async def fake_fetch(*, conn, limit):
        assert limit == 100
        return [_row()]

    async def fake_mark_published(*, conn, event_id):
        marked.append(event_id)

    monkeypatch.setattr(
        "mimir.outbox_publisher.get_connection",
        lambda: fake_connection_context(conn),
    )
    monkeypatch.setattr("mimir.outbox_publisher.fetch_unpublished_events", fake_fetch)
    monkeypatch.setattr("mimir.outbox_publisher.mark_published", fake_mark_published)

    producer = FakeProducer()
    claimed = await run_once(config=_config(), producer=producer)

    assert claimed == 1
    assert producer.published == [("mimir.changes.v1", EVENT_ID)]
    assert marked == [EVENT_ID]
    assert conn.commits == 1


@pytest.mark.asyncio
async def test_run_once_records_failure_without_marking_published(monkeypatch):
    conn = FakeConnection()
    marked = []
    failures = []

    async def fake_fetch(*, conn, limit):
        return [_row(publish_attempts=3)]

    async def fake_mark_published(*, conn, event_id):
        marked.append(event_id)

    async def fake_record_failure(*, conn, event_id, error, retry_after_seconds):
        failures.append((event_id, error, retry_after_seconds))

    monkeypatch.setattr(
        "mimir.outbox_publisher.get_connection",
        lambda: fake_connection_context(conn),
    )
    monkeypatch.setattr("mimir.outbox_publisher.fetch_unpublished_events", fake_fetch)
    monkeypatch.setattr("mimir.outbox_publisher.mark_published", fake_mark_published)
    monkeypatch.setattr(
        "mimir.outbox_publisher.record_publish_failure", fake_record_failure
    )

    claimed = await run_once(config=_config(), producer=FakeProducer(fail=True))

    assert claimed == 1
    assert marked == []
    assert failures == [(EVENT_ID, "broker unavailable", 8)]
    assert conn.commits == 1
