-- Mímir V2 Migration 005: Provenance Event
-- Append-only audit log for all changes

-- =============================================================================
-- PROVENANCE_EVENT TABLE - Audit trail
-- =============================================================================

CREATE TABLE mimirdata.provenance_event (
    id SERIAL PRIMARY KEY,
    tenant_id INT NOT NULL REFERENCES mimirdata.tenant(id) ON DELETE CASCADE,
    
    -- Entity affected (artifact or artifact_version only)
    entity_type mimirdata.entity_type NOT NULL,
    entity_id INT NOT NULL,
    
    -- Action details
    action mimirdata.provenance_action NOT NULL,
    actor_type mimirdata.provenance_actor_type NOT NULL,
    actor_id TEXT,                       -- Actor identifier (user ID, system name, etc.)
    actor_name TEXT,                     -- Actor display name
    reason TEXT,                         -- Why the action was taken
    correlation_id TEXT,                 -- Links related events (e.g., bulk import)
    
    -- Timestamp
    timestamp TIMESTAMPTZ NOT NULL DEFAULT now(),
    
    -- Action-specific details
    metadata JSONB DEFAULT '{}'::jsonb
);

-- Primary lookups
CREATE INDEX idx_provenance_event_tenant ON mimirdata.provenance_event (tenant_id);
CREATE INDEX idx_provenance_event_entity ON mimirdata.provenance_event (tenant_id, entity_type, entity_id);
CREATE INDEX idx_provenance_event_timestamp ON mimirdata.provenance_event (tenant_id, timestamp DESC);
CREATE INDEX idx_provenance_event_action ON mimirdata.provenance_event (tenant_id, action);
CREATE INDEX idx_provenance_event_actor ON mimirdata.provenance_event (tenant_id, actor_type, actor_id);
CREATE INDEX idx_provenance_event_correlation ON mimirdata.provenance_event (correlation_id)
    WHERE correlation_id IS NOT NULL;

COMMENT ON TABLE mimirdata.provenance_event IS 'Append-only audit log for all entity changes';
COMMENT ON COLUMN mimirdata.provenance_event.entity_type IS 'Type of entity affected (artifact or artifact_version)';
COMMENT ON COLUMN mimirdata.provenance_event.entity_id IS 'ID of the affected entity';
COMMENT ON COLUMN mimirdata.provenance_event.action IS 'What happened: create, update, delete, supersede, archive, restore';
COMMENT ON COLUMN mimirdata.provenance_event.actor_type IS 'Who performed the action: user, system, llm, api_client, migration';
COMMENT ON COLUMN mimirdata.provenance_event.correlation_id IS 'Groups related events (e.g., bulk import)';
