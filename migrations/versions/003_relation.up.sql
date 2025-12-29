-- Mímir V2 Migration 003: Relation
-- Connects artifacts with FK to relation_type vocabulary

-- =============================================================================
-- RELATION TABLE - Polymorphic relationships between entities
-- =============================================================================

CREATE TABLE mimirdata.relation (
    id SERIAL PRIMARY KEY,
    tenant_id INT NOT NULL REFERENCES mimirdata.tenant(id) ON DELETE CASCADE,
    
    -- Source entity
    source_type mimirdata.entity_type NOT NULL,
    source_id INT NOT NULL,
    
    -- Target entity
    target_type mimirdata.entity_type NOT NULL,
    target_id INT NOT NULL,
    
    -- Relation type (FK to vocabulary table)
    relation_type TEXT NOT NULL REFERENCES mimirdata.relation_type(code),
    
    -- Relation strength/confidence (optional)
    confidence FLOAT,                    -- 0.0 to 1.0 confidence score
    
    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    
    -- Extensible properties
    metadata JSONB DEFAULT '{}'::jsonb
);

-- Primary lookups - bidirectional queries
CREATE INDEX idx_relation_tenant ON mimirdata.relation (tenant_id);
CREATE INDEX idx_relation_source ON mimirdata.relation (tenant_id, source_type, source_id);
CREATE INDEX idx_relation_target ON mimirdata.relation (tenant_id, target_type, target_id);
CREATE INDEX idx_relation_type ON mimirdata.relation (tenant_id, relation_type);

-- Prevent exact duplicates
CREATE UNIQUE INDEX idx_relation_unique ON mimirdata.relation 
    (tenant_id, source_type, source_id, target_type, target_id, relation_type);

COMMENT ON TABLE mimirdata.relation IS 'Polymorphic relationships between artifacts and versions';
COMMENT ON COLUMN mimirdata.relation.relation_type IS 'FK to relation_type vocabulary table';
COMMENT ON COLUMN mimirdata.relation.confidence IS 'Optional confidence score 0.0-1.0 for probabilistic relations';
