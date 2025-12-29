-- Mímir V2 Migration 002: Artifact and Artifact Version
-- Core content storage with FK to artifact_type vocabulary

-- =============================================================================
-- ARTIFACT TABLE - Core content entity
-- =============================================================================

CREATE TABLE mimirdata.artifact (
    id SERIAL PRIMARY KEY,
    tenant_id INT NOT NULL REFERENCES mimirdata.tenant(id) ON DELETE CASCADE,
    artifact_type TEXT NOT NULL REFERENCES mimirdata.artifact_type(code),
    
    -- Hierarchy (self-referential for parent/child)
    parent_artifact_id INT REFERENCES mimirdata.artifact(id) ON DELETE SET NULL,
    
    -- Positional info (for chunks, quotes, highlights, etc.)
    start_offset INT,                    -- Character position start
    end_offset INT,                      -- Character position end
    position_metadata JSONB,             -- Additional position info (page, line, etc.)
    
    -- Content
    title TEXT,
    content TEXT,
    content_hash TEXT,                   -- For deduplication
    
    -- Source tracking
    source TEXT,                         -- Origin: 'import', 'manual', 'generated'
    source_system TEXT,                  -- External system: 'chatgpt', 'notion', etc.
    external_id TEXT,                    -- ID in source system
    
    -- Full-text search
    search_vector tsvector GENERATED ALWAYS AS (
        setweight(to_tsvector('english', coalesce(title, '')), 'A') ||
        setweight(to_tsvector('english', coalesce(content, '')), 'B')
    ) STORED,
    
    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    
    -- Extensible properties
    metadata JSONB DEFAULT '{}'::jsonb
);

-- Primary lookups
CREATE INDEX idx_artifact_tenant ON mimirdata.artifact (tenant_id);
CREATE INDEX idx_artifact_type ON mimirdata.artifact (tenant_id, artifact_type);
CREATE INDEX idx_artifact_parent ON mimirdata.artifact (parent_artifact_id) WHERE parent_artifact_id IS NOT NULL;

-- Source tracking indexes
CREATE INDEX idx_artifact_source ON mimirdata.artifact (tenant_id, source) WHERE source IS NOT NULL;
CREATE INDEX idx_artifact_source_system ON mimirdata.artifact (tenant_id, source_system) WHERE source_system IS NOT NULL;
CREATE UNIQUE INDEX idx_artifact_external_id ON mimirdata.artifact (tenant_id, source_system, external_id) 
    WHERE external_id IS NOT NULL;

-- Content deduplication
CREATE INDEX idx_artifact_content_hash ON mimirdata.artifact (tenant_id, content_hash) WHERE content_hash IS NOT NULL;

-- Full-text search index
CREATE INDEX idx_artifact_search ON mimirdata.artifact USING GIN (search_vector);

-- Timestamp for queries
CREATE INDEX idx_artifact_created ON mimirdata.artifact (tenant_id, created_at DESC);

COMMENT ON TABLE mimirdata.artifact IS 'Core content entity - all content types are artifacts';
COMMENT ON COLUMN mimirdata.artifact.artifact_type IS 'FK to artifact_type vocabulary table';
COMMENT ON COLUMN mimirdata.artifact.start_offset IS 'Character offset for positional types (chunk, quote, etc.)';
COMMENT ON COLUMN mimirdata.artifact.position_metadata IS 'Additional position info: page number, paragraph, etc.';

-- =============================================================================
-- ARTIFACT VERSION TABLE - Version history
-- =============================================================================

CREATE TABLE mimirdata.artifact_version (
    id SERIAL PRIMARY KEY,
    artifact_id INT NOT NULL REFERENCES mimirdata.artifact(id) ON DELETE CASCADE,
    version_number INT NOT NULL,
    
    -- Snapshot of content at this version
    title TEXT,
    content TEXT,
    content_hash TEXT,
    
    -- Change metadata
    change_reason TEXT,
    changed_by TEXT,
    
    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    
    -- Version metadata
    metadata JSONB DEFAULT '{}'::jsonb,
    
    UNIQUE (artifact_id, version_number)
);

CREATE INDEX idx_artifact_version_artifact ON mimirdata.artifact_version (artifact_id);
CREATE INDEX idx_artifact_version_created ON mimirdata.artifact_version (created_at DESC);

COMMENT ON TABLE mimirdata.artifact_version IS 'Immutable version history for artifacts';

-- =============================================================================
-- UPDATE TRIGGER - Auto-update updated_at
-- =============================================================================

CREATE OR REPLACE FUNCTION mimirdata.update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER artifact_updated_at
    BEFORE UPDATE ON mimirdata.artifact
    FOR EACH ROW
    EXECUTE FUNCTION mimirdata.update_updated_at();
