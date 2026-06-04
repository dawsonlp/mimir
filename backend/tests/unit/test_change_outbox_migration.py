"""Tests for the change outbox migration contract."""

from pathlib import Path

MIGRATIONS_DIR = Path(__file__).parents[2] / "migrations" / "versions"


def test_change_outbox_migration_defines_replay_schema():
    """Migration 008 should define the durable outbox and replay indexes."""
    sql = (MIGRATIONS_DIR / "008_change_outbox.up.sql").read_text()

    assert "CREATE TABLE mimirdata.change_outbox" in sql
    assert "id UUID PRIMARY KEY DEFAULT uuidv7()" in sql
    assert "sequence BIGINT GENERATED ALWAYS AS IDENTITY" in sql
    assert "payload JSONB NOT NULL DEFAULT '{}'::jsonb" in sql
    assert "published_at TIMESTAMPTZ" in sql
    assert "CHECK (action IN ('create'))" in sql
    assert "next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now()" in sql

    assert "idx_change_outbox_unpublished" in sql
    assert "ON mimirdata.change_outbox (next_attempt_at, sequence)" in sql
    assert "WHERE published_at IS NULL" in sql
    assert "idx_change_outbox_tenant_sequence" in sql
    assert "idx_change_outbox_tenant_entity" in sql


def test_change_outbox_down_migration_drops_table():
    """Down migration should cleanly drop the outbox table."""
    sql = (MIGRATIONS_DIR / "008_change_outbox.down.sql").read_text()

    assert "DROP TABLE IF EXISTS mimirdata.change_outbox CASCADE" in sql
