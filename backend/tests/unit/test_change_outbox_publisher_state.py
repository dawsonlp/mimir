"""Unit coverage for change outbox publisher state transitions."""

from datetime import UTC, datetime
from uuid import UUID

import pytest

from mimir.services import change_outbox

EVENT_ID = UUID("019e9052-cccc-7000-9000-000000000003")
ENTITY_ID = UUID("019e9052-aaaa-7000-9000-000000000001")
PROVENANCE_ID = UUID("019e9052-bbbb-7000-9000-000000000002")
OCCURRED_AT = datetime(2026, 6, 4, 1, 49, 24, 535000, tzinfo=UTC)


class FakeResult:
    def __init__(self, *, row=None, rows=None):
        self.row = row
        self.rows = rows or []

    async def fetchone(self):
        return self.row

    async def fetchall(self):
        return self.rows


class FakeConnection:
    def __init__(self):
        self.executed = []

    async def execute(self, sql, params=None):
        self.executed.append((sql, params))

        if "FROM mimirdata.change_outbox" in sql and "FOR UPDATE SKIP LOCKED" in sql:
            return FakeResult(
                rows=[
                    (
                        str(EVENT_ID),
                        1,
                        42,
                        "artifact",
                        str(ENTITY_ID),
                        "create",
                        OCCURRED_AT,
                        str(PROVENANCE_ID),
                        None,
                        "api_client",
                        None,
                        {"artifact_type": "document"},
                        2,
                        "previous failure",
                    )
                ]
            )

        if "COUNT(*)" in sql:
            return FakeResult(row=(3, 12.5))

        return FakeResult()


@pytest.mark.asyncio
async def test_fetch_unpublished_events_claims_due_rows_in_sequence_order():
    conn = FakeConnection()

    rows = await change_outbox.fetch_unpublished_events(conn=conn, limit=100)

    assert len(rows) == 1
    assert rows[0].event.event_id == EVENT_ID
    assert rows[0].event.sequence == 42
    assert rows[0].event.provenance_event_id == PROVENANCE_ID
    assert rows[0].publish_attempts == 2
    assert rows[0].last_error == "previous failure"

    sql, params = conn.executed[0]
    assert "published_at IS NULL" in sql
    assert "next_attempt_at <= now()" in sql
    assert "ORDER BY sequence" in sql
    assert "FOR UPDATE SKIP LOCKED" in sql
    assert params == (100,)


@pytest.mark.asyncio
async def test_mark_published_requires_unpublished_row():
    conn = FakeConnection()

    await change_outbox.mark_published(conn=conn, event_id=EVENT_ID)

    sql, params = conn.executed[0]
    assert "SET published_at = now()" in sql
    assert "last_error = NULL" in sql
    assert "published_at IS NULL" in sql
    assert params == (str(EVENT_ID),)


@pytest.mark.asyncio
async def test_record_publish_failure_increments_attempts_and_sets_retry_time():
    conn = FakeConnection()

    await change_outbox.record_publish_failure(
        conn=conn,
        event_id=EVENT_ID,
        error="broker unavailable",
        retry_after_seconds=30,
    )

    sql, params = conn.executed[0]
    assert "publish_attempts = publish_attempts + 1" in sql
    assert "last_error = %s" in sql
    assert "next_attempt_at = now() + (%s * interval '1 second')" in sql
    assert "published_at IS NULL" in sql
    assert params == ("broker unavailable", 30, str(EVENT_ID))


def test_calculate_retry_delay_seconds_is_bounded_exponential():
    assert change_outbox.calculate_retry_delay_seconds(0) == 1
    assert change_outbox.calculate_retry_delay_seconds(3) == 8
    assert change_outbox.calculate_retry_delay_seconds(10, max_seconds=300) == 300


@pytest.mark.parametrize(
    ("publish_attempts", "base_seconds", "max_seconds"),
    [(-1, 1, 300), (0, 0, 300), (0, 30, 10)],
)
def test_calculate_retry_delay_seconds_rejects_invalid_inputs(
    publish_attempts, base_seconds, max_seconds
):
    with pytest.raises(ValueError):
        change_outbox.calculate_retry_delay_seconds(
            publish_attempts,
            base_seconds=base_seconds,
            max_seconds=max_seconds,
        )


@pytest.mark.asyncio
async def test_get_outbox_status_reports_backlog_count_and_oldest_age():
    conn = FakeConnection()

    status = await change_outbox.get_outbox_status(conn=conn)

    assert status.unpublished_count == 3
    assert status.oldest_unpublished_age_seconds == 12.5
