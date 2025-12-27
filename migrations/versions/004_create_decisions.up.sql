-- Migration 004: Create decisions table
-- Decisions capture conclusions, choices, and resolutions

-- Decision status enum
CREATE TYPE mimirdata.decision_status AS ENUM (
    'active',       -- Current decision
    'superseded',   -- Replaced by newer decision
    'tentative'     -- Provisional, pending confirmation
);

-- Decision source enum (reuse pattern from intents)
CREATE TYPE mimirdata.decision_source AS ENUM (
    'user',         -- Human-created
    'llm_proposed', -- LLM suggested (requires acceptance)
    'system'        -- System-generated
);

-- Decisions table
CREATE TABLE mimirdata.decisions (
    id SERIAL PRIMARY KEY,
    tenant_id INT NOT NULL REFERENCES mimirdata.tenants(id) ON DELETE RESTRICT,
    artifact_id INT REFERENCES mimirdata.artifacts(id) ON DELETE SET NULL,
    intent_id INT REFERENCES mimirdata.intents(id) ON DELETE SET NULL,
    statement TEXT NOT NULL,
    rationale TEXT,
    status mimirdata.decision_status NOT NULL DEFAULT 'active',
    source mimirdata.decision_source NOT NULL DEFAULT 'user',
    superseded_by_id INT REFERENCES mimirdata.decisions(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

-- Indexes for decisions
CREATE INDEX idx_decisions_tenant ON mimirdata.decisions (tenant_id);
CREATE INDEX idx_decisions_artifact ON mimirdata.decisions (artifact_id) WHERE artifact_id IS NOT NULL;
CREATE INDEX idx_decisions_intent ON mimirdata.decisions (intent_id) WHERE intent_id IS NOT NULL;
CREATE INDEX idx_decisions_status ON mimirdata.decisions (status);
CREATE INDEX idx_decisions_superseded_by ON mimirdata.decisions (superseded_by_id) WHERE superseded_by_id IS NOT NULL;
CREATE INDEX idx_decisions_created_at ON mimirdata.decisions (created_at DESC);

-- Trigger to update updated_at on decisions
CREATE TRIGGER trg_decisions_updated_at
    BEFORE UPDATE ON mimirdata.decisions
    FOR EACH ROW
    EXECUTE FUNCTION mimirdata.update_updated_at();

-- Comments for documentation
COMMENT ON TABLE mimirdata.decisions IS 'Conclusions, choices, or resolutions from artifacts/conversations';
COMMENT ON COLUMN mimirdata.decisions.artifact_id IS 'Source artifact where decision emerged';
COMMENT ON COLUMN mimirdata.decisions.intent_id IS 'Intent this decision addresses';
COMMENT ON COLUMN mimirdata.decisions.statement IS 'The actual decision statement';
COMMENT ON COLUMN mimirdata.decisions.rationale IS 'Reasoning behind the decision';
COMMENT ON COLUMN mimirdata.decisions.status IS 'Lifecycle: active, superseded, tentative';
COMMENT ON COLUMN mimirdata.decisions.source IS 'Origin: user-created, LLM-proposed, or system-generated';
COMMENT ON COLUMN mimirdata.decisions.superseded_by_id IS 'FK to newer decision that replaces this one';
