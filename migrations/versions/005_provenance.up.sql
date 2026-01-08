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
    reason TEXT,                         -- Why the action was taken
    
    -- State snapshots for change tracking
    before_state JSONB,                  -- State before the action (for updates/deletes)
    after_state JSONB,                   -- State after the action (for creates/updates)
    
    -- Timestamp
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    
    -- Action-specific details
    metadata JSONB DEFAULT '{}'::jsonb
);

-- Primary lookups
CREATE INDEX idx_provenance_event_tenant ON mimirdata.provenance_event (tenant_id);
CREATE INDEX idx_provenance_event_entity ON mimirdata.provenance_event (tenant_id, entity_type, entity_id);
CREATE INDEX idx_provenance_event_created ON mimirdata.provenance_event (tenant_id, created_at DESC);
CREATE INDEX idx_provenance_event_action ON mimirdata.provenance_event (tenant_id, action);
CREATE INDEX idx_provenance_event_actor ON mimirdata.provenance_event (tenant_id, actor_type, actor_id);

COMMENT ON TABLE mimirdata.provenance_event IS 'Append-only audit log for all entity changes';
COMMENT ON COLUMN mimirdata.provenance_event.entity_type IS 'Type of entity affected (artifact or artifact_version)';
COMMENT ON COLUMN mimirdata.provenance_event.entity_id IS 'ID of the affected entity';
COMMENT ON COLUMN mimirdata.provenance_event.action IS 'What happened: create, update, delete, supersede, archive, restore';
COMMENT ON COLUMN mimirdata.provenance_event.actor_type IS 'Who performed the action: user, system, llm, api_client, migration';
COMMENT ON COLUMN mimirdata.provenance_event.before_state IS 'State before the action (for updates/deletes)';
COMMENT ON COLUMN mimirdata.provenance_event.after_state IS 'State after the action (for creates/updates)';