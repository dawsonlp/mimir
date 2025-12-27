-- Migration 006: Create relations table
-- Relations are connections between any two entities in the system

-- Entity type enum (what types can participate in relations)
CREATE TYPE mimirdata.entity_type AS ENUM (
    'artifact',
    'artifact_version',
    'intent',
    'intent_group',
    'decision',
    'span'
);

-- Relation type enum
CREATE TYPE mimirdata.relation_type AS ENUM (
    'references',     -- Source references target
    'supports',       -- Source provides evidence for target
    'contradicts',    -- Source contradicts target
    'derived_from',   -- Source was created from target
    'supersedes',     -- Source replaces target
    'related_to',     -- General association
    'parent_of',      -- Hierarchical parent
    'child_of',       -- Hierarchical child
    'implements',     -- Source implements target (decision→intent)
    'resolves'        -- Source resolves target (decision→intent)
);

-- Relations table (polymorphic connections)
CREATE TABLE mimirdata.relations (
    id SERIAL PRIMARY KEY,
    tenant_id INT NOT NULL REFERENCES mimirdata.tenants(id) ON DELETE RESTRICT,
    source_type mimirdata.entity_type NOT NULL,
    source_id INT NOT NULL,
    target_type mimirdata.entity_type NOT NULL,
    target_id INT NOT NULL,
    relation_type mimirdata.relation_type NOT NULL,
    description TEXT,
    confidence REAL,  -- Optional confidence score (0.0-1.0)
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    
    -- Prevent duplicate relations
    CONSTRAINT uq_relation UNIQUE (tenant_id, source_type, source_id, target_type, target_id, relation_type),
    -- Prevent self-references
    CONSTRAINT chk_no_self_relation CHECK (
        NOT (source_type = target_type AND source_id = target_id)
    ),
    -- Confidence must be valid if provided
    CONSTRAINT chk_confidence_range CHECK (
        confidence IS NULL OR (confidence >= 0.0 AND confidence <= 1.0)
    )
);

-- Indexes for relations
CREATE INDEX idx_relations_tenant ON mimirdata.relations (tenant_id);
CREATE INDEX idx_relations_source ON mimirdata.relations (source_type, source_id);
CREATE INDEX idx_relations_target ON mimirdata.relations (target_type, target_id);
CREATE INDEX idx_relations_type ON mimirdata.relations (relation_type);
CREATE INDEX idx_relations_created_at ON mimirdata.relations (created_at DESC);

-- Composite indexes for common queries
CREATE INDEX idx_relations_tenant_source ON mimirdata.relations (tenant_id, source_type, source_id);
CREATE INDEX idx_relations_tenant_target ON mimirdata.relations (tenant_id, target_type, target_id);

-- Trigger to update updated_at on relations
CREATE TRIGGER trg_relations_updated_at
    BEFORE UPDATE ON mimirdata.relations
    FOR EACH ROW
    EXECUTE FUNCTION mimirdata.update_updated_at();

-- Comments for documentation
COMMENT ON TABLE mimirdata.relations IS 'Polymorphic relations between any two entities';
COMMENT ON COLUMN mimirdata.relations.source_type IS 'Type of the source entity';
COMMENT ON COLUMN mimirdata.relations.source_id IS 'ID of the source entity';
COMMENT ON COLUMN mimirdata.relations.target_type IS 'Type of the target entity';
COMMENT ON COLUMN mimirdata.relations.target_id IS 'ID of the target entity';
COMMENT ON COLUMN mimirdata.relations.relation_type IS 'Type of relationship: references, supports, contradicts, etc.';
COMMENT ON COLUMN mimirdata.relations.confidence IS 'Optional confidence score for LLM-proposed relations (0.0-1.0)';
COMMENT ON COLUMN mimirdata.relations.description IS 'Optional description of the relationship';
