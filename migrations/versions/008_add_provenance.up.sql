-- Migration 008: Add provenance tracking for audit trails
-- Records who/what/when/why for all entity changes (append-only audit log)

-- Entity type enum (matches existing entity types in the system)
CREATE TYPE mimirdata.provenance_entity_type AS ENUM (
    'tenant',
    'artifact',
    'artifact_version',
    'intent',
    'intent_group',
    'decision',
    'span',
    'relation',
    'embedding'
);

-- Action type enum (what happened to the entity)
CREATE TYPE mimirdata.provenance_action AS ENUM (
    'create',
    'update',
    'delete',
    'supersede',
    'archive',
    'restore'
);

-- Actor type enum (who/what performed the action)
CREATE TYPE mimirdata.provenance_actor_type AS ENUM (
    'user',
    'system',
    'llm',
    'api_client',
    'migration'
);

-- Provenance events table (append-only audit log)
CREATE TABLE mimirdata.provenance_events (
    id SERIAL PRIMARY KEY,
    tenant_id INT NOT NULL REFERENCES mimirdata.tenants(id) ON DELETE RESTRICT,
    
    -- What entity was affected
    entity_type mimirdata.provenance_entity_type NOT NULL,
    entity_id INT NOT NULL,
    
    -- What action was performed
    action mimirdata.provenance_action NOT NULL,
    
    -- Who/what performed the action
    actor_type mimirdata.provenance_actor_type NOT NULL,
    actor_id VARCHAR(255),           -- User ID, system name, or LLM model name
    actor_name VARCHAR(255),          -- Human-readable actor name
    
    -- When and why
    timestamp TIMESTAMPTZ NOT NULL DEFAULT now(),
    reason TEXT,                      -- Why the action was performed
    
    -- Additional context
    changes JSONB,                    -- Before/after values for updates
    metadata JSONB DEFAULT '{}',      -- Additional structured data
    related_entity_type mimirdata.provenance_entity_type,  -- For linked operations
    related_entity_id INT,            -- ID of related entity (e.g., superseding decision)
    correlation_id VARCHAR(255),      -- To link related provenance events
    request_id VARCHAR(255),          -- HTTP request ID for tracing
    
    -- Note: No updated_at - provenance events are immutable
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Primary lookup: entity history (most common query)
CREATE INDEX idx_provenance_entity ON mimirdata.provenance_events (entity_type, entity_id, timestamp DESC);

-- Tenant-scoped queries
CREATE INDEX idx_provenance_tenant ON mimirdata.provenance_events (tenant_id);
CREATE INDEX idx_provenance_tenant_timestamp ON mimirdata.provenance_events (tenant_id, timestamp DESC);

-- Filter by actor
CREATE INDEX idx_provenance_actor ON mimirdata.provenance_events (actor_type, actor_id);

-- Filter by action
CREATE INDEX idx_provenance_action ON mimirdata.provenance_events (action);

-- Time-based queries
CREATE INDEX idx_provenance_timestamp ON mimirdata.provenance_events (timestamp DESC);

-- Correlation tracking
CREATE INDEX idx_provenance_correlation ON mimirdata.provenance_events (correlation_id) 
    WHERE correlation_id IS NOT NULL;

-- Request tracing
CREATE INDEX idx_provenance_request ON mimirdata.provenance_events (request_id) 
    WHERE request_id IS NOT NULL;

-- Related entity lookup
CREATE INDEX idx_provenance_related ON mimirdata.provenance_events (related_entity_type, related_entity_id)
    WHERE related_entity_type IS NOT NULL;

-- Comments for documentation
COMMENT ON TABLE mimirdata.provenance_events IS 'Append-only audit log tracking who/what/when/why for all entity changes';
COMMENT ON COLUMN mimirdata.provenance_events.entity_type IS 'Type of entity that was modified';
COMMENT ON COLUMN mimirdata.provenance_events.entity_id IS 'ID of the entity that was modified';
COMMENT ON COLUMN mimirdata.provenance_events.action IS 'Type of action performed (create, update, delete, supersede, etc.)';
COMMENT ON COLUMN mimirdata.provenance_events.actor_type IS 'Type of actor who performed the action (user, system, llm, etc.)';
COMMENT ON COLUMN mimirdata.provenance_events.actor_id IS 'Unique identifier of the actor (user ID, system name, model name)';
COMMENT ON COLUMN mimirdata.provenance_events.actor_name IS 'Human-readable name of the actor';
COMMENT ON COLUMN mimirdata.provenance_events.reason IS 'Explanation of why the action was performed';
COMMENT ON COLUMN mimirdata.provenance_events.changes IS 'JSON object containing before/after values for updates';
COMMENT ON COLUMN mimirdata.provenance_events.metadata IS 'Additional structured data about the event';
COMMENT ON COLUMN mimirdata.provenance_events.related_entity_type IS 'Type of related entity (e.g., new decision in supersede)';
COMMENT ON COLUMN mimirdata.provenance_events.related_entity_id IS 'ID of related entity';
COMMENT ON COLUMN mimirdata.provenance_events.correlation_id IS 'UUID to link related provenance events';
COMMENT ON COLUMN mimirdata.provenance_events.request_id IS 'HTTP request ID for distributed tracing';
