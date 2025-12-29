-- Mímir V2 Migration 002: Artifact and Artifact Version
-- Creates the core content tables with full-text search support

-- =============================================================================
-- ARTIFACT TABLE - All content (raw and derived)
-- =============================================================================

CREATE TABLE mimirdata.artifact (
    id SERIAL PRIMARY KEY,
    tenant_id INT NOT NULL REFERENCES mimirdata.tenant(id) ON DELETE CASCADE,
    artifact_type mimirdata.artifact_type NOT NULL,
    external_id TEXT,                    -- Original source ID (e.g., ChatGPT conversation ID)
    source TEXT,                         -- Origin category (import, api, user, derived)
    source_system TEXT,                  -- External system name (chatgpt, confluence, github)
    title TEXT,                          -- Optional title/summary
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata JSONB DEFAULT '{}'::jsonb,  -- Type-specific fields (status, rationale, etc.)
    search_vector TSVECTOR               -- Full-text search index
);

-- Primary lookups
CREATE INDEX idx_artifact_tenant ON mimirdata.artifact (tenant_id);
CREATE INDEX idx_artifact_type ON mimirdata.artifact (tenant_id, artifact_type);
CREATE INDEX idx_artifact_source ON mimirdata.artifact (tenant_id, source);
CREATE INDEX idx_artifact_source_system ON mimirdata.artifact (tenant_id, source_system);
CREATE INDEX idx_artifact_created ON mimirdata.artifact (tenant_id, created_at DESC);

-- External ID lookup (for deduplication during import)
CREATE INDEX idx_artifact_external_id ON mimirdata.artifact (tenant_id, source_system, external_id)
    WHERE external_id IS NOT NULL;

-- Full-text search (GIN index)
CREATE INDEX idx_artifact_search ON mimirdata.artifact USING GIN (search_vector);

-- JSONB metadata queries
CREATE INDEX idx_artifact_metadata ON mimirdata.artifact USING GIN (metadata);

COMMENT ON TABLE mimirdata.artifact IS 'All content - raw and derived - with type discrimination';
COMMENT ON COLUMN mimirdata.artifact.artifact_type IS 'Type discriminator for content category';
COMMENT ON COLUMN mimirdata.artifact.external_id IS 'Original ID from source system for deduplication';
COMMENT ON COLUMN mimirdata.artifact.source IS 'How the artifact was created: import, api, user, derived';
COMMENT ON COLUMN mimirdata.artifact.source_system IS 'External system name: chatgpt, confluence, github, etc.';
COMMENT ON COLUMN mimirdata.artifact.search_vector IS 'Precomputed tsvector for full-text search';

-- =============================================================================
-- ARTIFACT_VERSION TABLE - Append-only content history
-- =============================================================================

CREATE TABLE mimirdata.artifact_version (
    id SERIAL PRIMARY KEY,
    artifact_id INT NOT NULL REFERENCES mimirdata.artifact(id) ON DELETE CASCADE,
    version_number INT NOT NULL,
    content TEXT NOT NULL,               -- Full content for this version
    content_hash TEXT,                   -- SHA-256 for deduplication
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by TEXT                      -- User or system that created this version
);

-- Ensure unique version numbers per artifact
ALTER TABLE mimirdata.artifact_version 
    ADD CONSTRAINT artifact_version_unique_version UNIQUE (artifact_id, version_number);

-- Primary lookups
CREATE INDEX idx_artifact_version_artifact ON mimirdata.artifact_version (artifact_id);
CREATE INDEX idx_artifact_version_hash ON mimirdata.artifact_version (content_hash)
    WHERE content_hash IS NOT NULL;

COMMENT ON TABLE mimirdata.artifact_version IS 'Append-only content history - content is never overwritten';
COMMENT ON COLUMN mimirdata.artifact_version.version_number IS 'Sequential version (1, 2, 3...)';
COMMENT ON COLUMN mimirdata.artifact_version.content_hash IS 'SHA-256 hash for content deduplication';
COMMENT ON COLUMN mimirdata.artifact_version.created_by IS 'User or system identifier that created this version';

-- =============================================================================
-- TRIGGER: Auto-update search_vector on artifact insert/update
-- =============================================================================

CREATE OR REPLACE FUNCTION mimirdata.update_artifact_search_vector()
RETURNS TRIGGER AS $$
BEGIN
    NEW.search_vector := to_tsvector('english', COALESCE(NEW.title, ''));
    NEW.updated_at := now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_artifact_search_vector
    BEFORE INSERT OR UPDATE ON mimirdata.artifact
    FOR EACH ROW
    EXECUTE FUNCTION mimirdata.update_artifact_search_vector();

-- =============================================================================
-- TRIGGER: Update artifact's search_vector when version content changes
-- =============================================================================

CREATE OR REPLACE FUNCTION mimirdata.update_artifact_from_version()
RETURNS TRIGGER AS $$
DECLARE
    artifact_title TEXT;
BEGIN
    -- Get the artifact's title
    SELECT title INTO artifact_title
    FROM mimirdata.artifact
    WHERE id = NEW.artifact_id;
    
    -- Update the artifact's search_vector with combined title + content
    UPDATE mimirdata.artifact
    SET search_vector = to_tsvector('english', 
            COALESCE(artifact_title, '') || ' ' || COALESCE(NEW.content, '')),
        updated_at = now()
    WHERE id = NEW.artifact_id;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_artifact_version_search
    AFTER INSERT ON mimirdata.artifact_version
    FOR EACH ROW
    EXECUTE FUNCTION mimirdata.update_artifact_from_version();
