-- Mímir V2 Migration 003: Relation
-- Polymorphic connections between entities

-- =============================================================================
-- RELATION TABLE - Connects any two entities
-- =============================================================================

CREATE TABLE mimirdata.relation (
    id SERIAL PRIMARY KEY,
    tenant_id INT NOT NULL REFERENCES mimirdata.tenant(id) ON DELETE CASCADE,
    source_type mimirdata.entity_type NOT NULL,
    source_id INT NOT NULL,
    target_type mimirdata.entity_type NOT NULL,
    target_id INT NOT NULL,
    relation_type mimirdata.relation_type NOT NULL,
    description TEXT,
    confidence REAL CHECK (confidence IS NULL OR (confidence >= 0.0 AND confidence <= 1.0)),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata JSONB DEFAULT '{}'::jsonb,
    
    -- Prevent self-referencing relations
    CONSTRAINT relation_no_self_reference CHECK (
        NOT (source_type = target_type AND source_id = target_id)
    )
);

-- Index for source lookups (find all relations FROM an entity)
CREATE INDEX idx_relation_source ON mimirdata.relation (tenant_id, source_type, source_id);

-- Index for target lookups (find all relations TO an entity)
CREATE INDEX idx_relation_target ON mimirdata.relation (tenant_id, target_type, target_id);

-- Index for relation type queries
CREATE INDEX idx_relation_type ON mimirdata.relation (tenant_id, relation_type);

-- Composite index for bidirectional queries
CREATE INDEX idx_relation_bidirectional ON mimirdata.relation (
    tenant_id, 
    source_type, source_id, 
    target_type, target_id
);

COMMENT ON TABLE mimirdata.relation IS 'Polymorphic connections between any two entities';
COMMENT ON COLUMN mimirdata.relation.source_type IS 'Entity type of the source (artifact, artifact_version, span)';
COMMENT ON COLUMN mimirdata.relation.target_type IS 'Entity type of the target (artifact, artifact_version, span)';
COMMENT ON COLUMN mimirdata.relation.relation_type IS 'Type of relationship between entities';
COMMENT ON COLUMN mimirdata.relation.confidence IS 'Confidence score 0.0-1.0 for LLM-proposed relations';
