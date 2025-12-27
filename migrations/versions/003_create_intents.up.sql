-- Migration 003: Create intent_groups and intents tables
-- Intent capture for user goals and questions

-- Intent status enum
CREATE TYPE mimirdata.intent_status AS ENUM (
    'active',       -- Currently being pursued
    'resolved',     -- Goal achieved
    'parked',       -- Temporarily set aside
    'abandoned'     -- No longer pursuing
);

-- Intent source enum
CREATE TYPE mimirdata.intent_source AS ENUM (
    'user',         -- Human-created
    'llm_proposed', -- LLM suggested (requires acceptance)
    'system'        -- System-generated
);

-- Intent Groups table (clusters of related intents)
CREATE TABLE mimirdata.intent_groups (
    id SERIAL PRIMARY KEY,
    tenant_id INT NOT NULL REFERENCES mimirdata.tenants(id) ON DELETE RESTRICT,
    name TEXT NOT NULL,
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    
    -- Unique name per tenant
    CONSTRAINT uq_intent_group_name_tenant UNIQUE (tenant_id, name)
);

-- Intents table (user goals/questions)
CREATE TABLE mimirdata.intents (
    id SERIAL PRIMARY KEY,
    tenant_id INT NOT NULL REFERENCES mimirdata.tenants(id) ON DELETE RESTRICT,
    intent_group_id INT REFERENCES mimirdata.intent_groups(id) ON DELETE SET NULL,
    artifact_id INT REFERENCES mimirdata.artifacts(id) ON DELETE SET NULL,
    title TEXT NOT NULL,
    description TEXT,
    status mimirdata.intent_status NOT NULL DEFAULT 'active',
    source mimirdata.intent_source NOT NULL DEFAULT 'user',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at TIMESTAMPTZ,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

-- Indexes for intent_groups
CREATE INDEX idx_intent_groups_tenant ON mimirdata.intent_groups (tenant_id);
CREATE INDEX idx_intent_groups_name ON mimirdata.intent_groups (name);

-- Indexes for intents
CREATE INDEX idx_intents_tenant ON mimirdata.intents (tenant_id);
CREATE INDEX idx_intents_group ON mimirdata.intents (intent_group_id) WHERE intent_group_id IS NOT NULL;
CREATE INDEX idx_intents_artifact ON mimirdata.intents (artifact_id) WHERE artifact_id IS NOT NULL;
CREATE INDEX idx_intents_status ON mimirdata.intents (status);
CREATE INDEX idx_intents_created_at ON mimirdata.intents (created_at DESC);

-- Trigger to update updated_at on intent_groups
CREATE TRIGGER trg_intent_groups_updated_at
    BEFORE UPDATE ON mimirdata.intent_groups
    FOR EACH ROW
    EXECUTE FUNCTION mimirdata.update_updated_at();

-- Trigger to update updated_at on intents
CREATE TRIGGER trg_intents_updated_at
    BEFORE UPDATE ON mimirdata.intents
    FOR EACH ROW
    EXECUTE FUNCTION mimirdata.update_updated_at();

-- Comments for documentation
COMMENT ON TABLE mimirdata.intent_groups IS 'Clusters of related intents (projects, research threads)';
COMMENT ON COLUMN mimirdata.intent_groups.name IS 'Unique name within tenant for the intent group';

COMMENT ON TABLE mimirdata.intents IS 'User goals or questions that initiated conversations/artifacts';
COMMENT ON COLUMN mimirdata.intents.intent_group_id IS 'Optional grouping for related intents';
COMMENT ON COLUMN mimirdata.intents.artifact_id IS 'Optional source artifact that spawned this intent';
COMMENT ON COLUMN mimirdata.intents.status IS 'Lifecycle status: active, resolved, parked, abandoned';
COMMENT ON COLUMN mimirdata.intents.source IS 'Origin: user-created, LLM-proposed, or system-generated';
COMMENT ON COLUMN mimirdata.intents.resolved_at IS 'Timestamp when intent was marked resolved';
