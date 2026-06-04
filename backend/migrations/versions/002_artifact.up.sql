-- Mímir V2 Migration 002: Artifact
-- Core content entity with UUID primary key (append-only)

-- =============================================================================
-- ARTIFACT TABLE - Core content entity (Append-Only)
-- =============================================================================

CREATE TABLE mimirdata.artifact (
    id UUID PRIMARY KEY DEFAULT uuidv7(),
    tenant_id INT NOT NULL REFERENCES mimirdata.tenant(id) ON DELETE CASCADE,
    artifact_type TEXT NOT NULL REFERENCES mimirdata.artifact_type(code),
    
    -- Hierarchy (self-referential for parent/child)
    parent_artifact_id UUID REFERENCES mimirdata.artifact(id) ON DELETE SET NULL,
    
    -- Positional info (for chunks, quotes, highlights, etc.)
    start_offset INT,                    -- Character position start
    end_offset INT,                      -- Character position end
    position_metadata JSONB,             -- Additional position info (page, line, etc.)
    
    -- Content
    title TEXT,
    content TEXT,
    content_hash TEXT,                   -- SHA-256 for queries (not unique constraint)
    
    -- Source tracking
    source TEXT,                         -- Origin: 'import', 'manual', 'generated'
    source_system TEXT,                  -- External system: 'chatgpt', 'notion', etc.
    external_id TEXT,                    -- ID in source system
    
    -- Full-text search
    search_vector tsvector GENERATED ALWAYS AS (
        setweight(to_tsvector('english', coalesce(title, '')), 'A') ||
        setweight(to_tsvector('english', coalesce(content, '')), 'B')
    ) STORED,
    
    -- Timestamp (no updated_at - append only)
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    
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

-- Content hash for duplicate queries (not unique - same content may exist in different contexts)
CREATE INDEX idx_artifact_content_hash ON mimirdata.artifact (tenant_id, content_hash) WHERE content_hash IS NOT NULL;

-- Full-text search index
CREATE INDEX idx_artifact_search ON mimirdata.artifact USING GIN (search_vector);

-- Timestamp for queries (UUIDv7 provides ordering, but explicit index is useful)
CREATE INDEX idx_artifact_created ON mimirdata.artifact (tenant_id, created_at DESC);

COMMENT ON TABLE mimirdata.artifact IS 'Core content entity - all content types are artifacts (append-only)';
COMMENT ON COLUMN mimirdata.artifact.id IS 'UUIDv7 primary key - client-generated preferred, or server uuidv7()';
COMMENT ON COLUMN mimirdata.artifact.artifact_type IS 'FK to artifact_type vocabulary table';
COMMENT ON COLUMN mimirdata.artifact.parent_artifact_id IS 'Parent artifact for positional types (chunk, quote, etc.)';
COMMENT ON COLUMN mimirdata.artifact.start_offset IS 'Character offset for positional types';
COMMENT ON COLUMN mimirdata.artifact.position_metadata IS 'Additional position info: page number, paragraph, etc.';
COMMENT ON COLUMN mimirdata.artifact.content_hash IS 'SHA-256 hash for duplicate queries (not enforced unique)';
