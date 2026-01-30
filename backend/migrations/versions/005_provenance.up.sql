-- Mímir V2 Migration 005: Provenance Event
-- Audit log for all creates (append-only)

-- =============================================================================
-- PROVENANCE_EVENT TABLE - Audit trail (Append-Only)
-- =============================================================================

CREATE TABLE mimirdata.provenance_event (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id INT NOT NULL REFERENCES mimirdata.tenant(id) ON DELETE CASCADE,
    
    -- Entity affected (artifact, relation, or embedding)
    entity_type TEXT NOT NULL,           -- 'artifact', 'relation', 'embedding'
    entity_id UUID NOT NULL,
    
    -- Action details (only 'create' for now - append-only system)
    action TEXT NOT NULL DEFAULT 'create',  -- 'create' only for now
    actor_type TEXT NOT NULL,            -- 'user', 'system', 'llm', 'api_client', 'migration'
    actor_id TEXT,                       -- Actor identifier (user ID, system name, etc.)
    reason TEXT,                         -- Why the action was taken
    
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

COMMENT ON TABLE mimirdata.provenance_event IS 'Audit log for entity creates (append-only)';
COMMENT ON COLUMN mimirdata.provenance_event.entity_type IS 'Type of entity: artifact, relation, embedding';
COMMENT ON COLUMN mimirdata.provenance_event.entity_id IS 'UUID of the affected entity';
COMMENT ON COLUMN mimirdata.provenance_event.action IS 'What happened: create (only action for now)';
COMMENT ON COLUMN mimirdata.provenance_event.actor_type IS 'Who performed the action: user, system, llm, api_client, migration';
