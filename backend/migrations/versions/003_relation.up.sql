-- Mímir V2 Migration 003: Relation
-- Connects artifacts with UUID references (append-only)

-- =============================================================================
-- RELATION TABLE - Connections between artifacts (Append-Only)
-- =============================================================================

CREATE TABLE mimirdata.relation (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id INT NOT NULL REFERENCES mimirdata.tenant(id) ON DELETE CASCADE,
    
    -- Source and target artifacts (UUID references)
    source_id UUID NOT NULL REFERENCES mimirdata.artifact(id) ON DELETE CASCADE,
    target_id UUID NOT NULL REFERENCES mimirdata.artifact(id) ON DELETE CASCADE,
    
    -- Relation type (FK to vocabulary table)
    relation_type TEXT NOT NULL REFERENCES mimirdata.relation_type(code),
    
    -- Relation strength/confidence (optional)
    confidence FLOAT,                    -- 0.0 to 1.0 confidence score
    
    -- Timestamp (no updated_at - append only)
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    
    -- Extensible properties
    metadata JSONB DEFAULT '{}'::jsonb
);

-- Primary lookups - bidirectional queries
CREATE INDEX idx_relation_tenant ON mimirdata.relation (tenant_id);
CREATE INDEX idx_relation_source ON mimirdata.relation (tenant_id, source_id);
CREATE INDEX idx_relation_target ON mimirdata.relation (tenant_id, target_id);
CREATE INDEX idx_relation_type ON mimirdata.relation (tenant_id, relation_type);

-- Prevent exact duplicates (same source, target, relation_type)
CREATE UNIQUE INDEX idx_relation_unique ON mimirdata.relation 
    (tenant_id, source_id, target_id, relation_type);

-- Timestamp for queries
CREATE INDEX idx_relation_created ON mimirdata.relation (tenant_id, created_at DESC);

COMMENT ON TABLE mimirdata.relation IS 'Connections between artifacts (append-only)';
COMMENT ON COLUMN mimirdata.relation.id IS 'UUID primary key - client-generated UUIDv7 preferred';
COMMENT ON COLUMN mimirdata.relation.relation_type IS 'FK to relation_type vocabulary table';
COMMENT ON COLUMN mimirdata.relation.confidence IS 'Optional confidence score 0.0-1.0 for LLM-proposed relations';
