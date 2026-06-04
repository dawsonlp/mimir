-- Mimir Migration 008: Change Outbox
-- Durable substrate change-event ledger for external projections.
-- See docs/change-outbox-architecture.md.

CREATE TABLE mimirdata.change_outbox (
    id UUID PRIMARY KEY DEFAULT uuidv7(),
    tenant_id INT NOT NULL REFERENCES mimirdata.tenant(id) ON DELETE CASCADE,

    -- Changed Mimir substrate entity.
    entity_type TEXT NOT NULL,
    entity_id UUID NOT NULL,
    action TEXT NOT NULL,

    -- Ordering and replay cursor.
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    sequence BIGINT GENERATED ALWAYS AS IDENTITY,

    -- Provenance/correlation context.
    provenance_event_id UUID,
    correlation_id UUID,
    actor_type TEXT,
    actor_id TEXT,

    -- Compact entity-specific facts for consumers.
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,

    -- Publication state. Published rows remain retained for replay/backfill.
    published_at TIMESTAMPTZ,
    publish_attempts INT NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_error TEXT,

    CONSTRAINT change_outbox_action_check
        CHECK (action IN ('create'))
);

CREATE INDEX idx_change_outbox_unpublished
ON mimirdata.change_outbox (next_attempt_at, sequence)
WHERE published_at IS NULL;

CREATE INDEX idx_change_outbox_tenant_sequence
ON mimirdata.change_outbox (tenant_id, sequence);

CREATE INDEX idx_change_outbox_tenant_entity
ON mimirdata.change_outbox (tenant_id, entity_type, entity_id);

COMMENT ON TABLE mimirdata.change_outbox IS
    'Durable change-event outbox for committed Mimir substrate writes';
COMMENT ON COLUMN mimirdata.change_outbox.id IS
    'UUIDv7 event id; consumers use this for at-least-once deduplication';
COMMENT ON COLUMN mimirdata.change_outbox.sequence IS
    'Global replay cursor for retained outbox rows';
COMMENT ON COLUMN mimirdata.change_outbox.payload IS
    'Compact entity-specific facts; does not duplicate full Mimir rows by default';
COMMENT ON COLUMN mimirdata.change_outbox.published_at IS
    'Set only after publisher receives Kafka acknowledgement; retained after publish';
COMMENT ON COLUMN mimirdata.change_outbox.next_attempt_at IS
    'Earliest time an unpublished row should be retried by the publisher';
