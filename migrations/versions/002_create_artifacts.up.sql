-- Migration 002: Create artifacts and artifact_versions tables
-- Core storage entities for conversations, documents, and notes

-- Artifact type enum
CREATE TYPE mimirdata.artifact_type AS ENUM (
    'conversation',  -- Chat logs, discussions
    'document',      -- Structured documents
    'note'           -- Freeform notes
);

-- Artifacts table (main entity)
CREATE TABLE mimirdata.artifacts (
    id SERIAL PRIMARY KEY,
    tenant_id INT NOT NULL REFERENCES mimirdata.tenants(id) ON DELETE RESTRICT,
    artifact_type mimirdata.artifact_type NOT NULL,
    external_id TEXT,           -- Original source ID (e.g., ChatGPT conversation ID)
    source TEXT NOT NULL,       -- e.g., 'chatgpt_export', 'user_upload', 'api'
    title TEXT,                 -- Optional title/summary
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

-- Artifact versions table (append-only)
CREATE TABLE mimirdata.artifact_versions (
    id SERIAL PRIMARY KEY,
    artifact_id INT NOT NULL REFERENCES mimirdata.artifacts(id) ON DELETE CASCADE,
    version_number INT NOT NULL,
    content TEXT NOT NULL,              -- Canonical raw content
    content_hash TEXT NOT NULL,         -- SHA-256 for deduplication
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by TEXT NOT NULL DEFAULT 'system',  -- User or system identifier
    
    -- Ensure version numbers are unique per artifact and sequential
    CONSTRAINT uq_artifact_version UNIQUE (artifact_id, version_number)
);

-- Indexes for artifacts
CREATE INDEX idx_artifacts_tenant ON mimirdata.artifacts (tenant_id);
CREATE INDEX idx_artifacts_type ON mimirdata.artifacts (artifact_type);
CREATE INDEX idx_artifacts_source ON mimirdata.artifacts (source);
CREATE INDEX idx_artifacts_external_id ON mimirdata.artifacts (external_id) WHERE external_id IS NOT NULL;
CREATE INDEX idx_artifacts_created_at ON mimirdata.artifacts (created_at DESC);

-- Indexes for artifact_versions
CREATE INDEX idx_artifact_versions_artifact ON mimirdata.artifact_versions (artifact_id);
CREATE INDEX idx_artifact_versions_hash ON mimirdata.artifact_versions (content_hash);

-- Trigger to update updated_at on artifacts
CREATE OR REPLACE FUNCTION mimirdata.update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_artifacts_updated_at
    BEFORE UPDATE ON mimirdata.artifacts
    FOR EACH ROW
    EXECUTE FUNCTION mimirdata.update_updated_at();

-- Comments for documentation
COMMENT ON TABLE mimirdata.artifacts IS 'Primary storage entity for conversations, documents, and notes';
COMMENT ON COLUMN mimirdata.artifacts.tenant_id IS 'FK to tenants for multi-tenant data isolation';
COMMENT ON COLUMN mimirdata.artifacts.external_id IS 'Original ID from source system (e.g., ChatGPT conversation ID)';
COMMENT ON COLUMN mimirdata.artifacts.source IS 'Origin of the artifact: chatgpt_export, user_upload, api, etc.';

COMMENT ON TABLE mimirdata.artifact_versions IS 'Append-only version history for artifacts';
COMMENT ON COLUMN mimirdata.artifact_versions.content_hash IS 'SHA-256 hash for content deduplication';
COMMENT ON COLUMN mimirdata.artifact_versions.created_by IS 'User or system identifier that created this version';
