-- Mímir V2 Migration 004: Span
-- Positional annotations within artifact content

-- =============================================================================
-- SPAN TABLE - Annotations within content
-- =============================================================================

CREATE TABLE mimirdata.span (
    id SERIAL PRIMARY KEY,
    tenant_id INT NOT NULL REFERENCES mimirdata.tenant(id) ON DELETE CASCADE,
    artifact_id INT NOT NULL REFERENCES mimirdata.artifact(id) ON DELETE CASCADE,
    artifact_version_id INT REFERENCES mimirdata.artifact_version(id) ON DELETE SET NULL,
    span_type mimirdata.span_type NOT NULL,
    start_offset INT NOT NULL CHECK (start_offset >= 0),
    end_offset INT NOT NULL CHECK (end_offset >= 0),
    content TEXT,                        -- The selected/annotated text
    annotation TEXT,                     -- Optional commentary
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata JSONB DEFAULT '{}'::jsonb,
    
    -- Ensure end_offset >= start_offset
    CONSTRAINT span_valid_offsets CHECK (end_offset >= start_offset)
);

-- Primary lookups
CREATE INDEX idx_span_tenant ON mimirdata.span (tenant_id);
CREATE INDEX idx_span_artifact ON mimirdata.span (artifact_id);
CREATE INDEX idx_span_artifact_version ON mimirdata.span (artifact_version_id)
    WHERE artifact_version_id IS NOT NULL;
CREATE INDEX idx_span_type ON mimirdata.span (tenant_id, span_type);

-- Offset range lookups (for finding spans at a position)
CREATE INDEX idx_span_offsets ON mimirdata.span (artifact_id, start_offset, end_offset);

COMMENT ON TABLE mimirdata.span IS 'Positional annotations within artifact content';
COMMENT ON COLUMN mimirdata.span.artifact_version_id IS 'Optional FK to specific version (NULL = latest)';
COMMENT ON COLUMN mimirdata.span.start_offset IS 'Character position start (0-indexed)';
COMMENT ON COLUMN mimirdata.span.end_offset IS 'Character position end (exclusive)';
COMMENT ON COLUMN mimirdata.span.content IS 'The selected/annotated text content';
COMMENT ON COLUMN mimirdata.span.annotation IS 'Optional user commentary on the span';
