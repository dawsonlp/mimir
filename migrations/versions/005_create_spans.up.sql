-- Migration 005: Create spans table
-- Spans are marked sections within artifacts (quotes, highlights, annotations)

-- Span type enum
CREATE TYPE mimirdata.span_type AS ENUM (
    'quote',        -- Exact text selection
    'highlight',    -- Emphasized section
    'annotation',   -- Commentary on a section
    'reference',    -- Reference marker
    'bookmark'      -- Saved position
);

-- Spans table
CREATE TABLE mimirdata.spans (
    id SERIAL PRIMARY KEY,
    tenant_id INT NOT NULL REFERENCES mimirdata.tenants(id) ON DELETE RESTRICT,
    artifact_id INT NOT NULL REFERENCES mimirdata.artifacts(id) ON DELETE CASCADE,
    artifact_version_id INT REFERENCES mimirdata.artifact_versions(id) ON DELETE SET NULL,
    span_type mimirdata.span_type NOT NULL DEFAULT 'quote',
    start_offset INT NOT NULL,
    end_offset INT NOT NULL,
    content TEXT,  -- The actual selected text (denormalized for convenience)
    annotation TEXT,  -- User's note about this span
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    
    -- Ensure valid range
    CONSTRAINT chk_span_range CHECK (start_offset >= 0 AND end_offset >= start_offset)
);

-- Indexes for spans
CREATE INDEX idx_spans_tenant ON mimirdata.spans (tenant_id);
CREATE INDEX idx_spans_artifact ON mimirdata.spans (artifact_id);
CREATE INDEX idx_spans_version ON mimirdata.spans (artifact_version_id) WHERE artifact_version_id IS NOT NULL;
CREATE INDEX idx_spans_type ON mimirdata.spans (span_type);
CREATE INDEX idx_spans_created_at ON mimirdata.spans (created_at DESC);
CREATE INDEX idx_spans_range ON mimirdata.spans (artifact_id, start_offset, end_offset);

-- Trigger to update updated_at on spans
CREATE TRIGGER trg_spans_updated_at
    BEFORE UPDATE ON mimirdata.spans
    FOR EACH ROW
    EXECUTE FUNCTION mimirdata.update_updated_at();

-- Comments for documentation
COMMENT ON TABLE mimirdata.spans IS 'Marked sections within artifacts (quotes, highlights, annotations)';
COMMENT ON COLUMN mimirdata.spans.artifact_id IS 'The artifact this span belongs to';
COMMENT ON COLUMN mimirdata.spans.artifact_version_id IS 'Optional specific version (offsets may shift between versions)';
COMMENT ON COLUMN mimirdata.spans.span_type IS 'Type of span: quote, highlight, annotation, reference, bookmark';
COMMENT ON COLUMN mimirdata.spans.start_offset IS 'Start character offset in artifact content';
COMMENT ON COLUMN mimirdata.spans.end_offset IS 'End character offset (exclusive) in artifact content';
COMMENT ON COLUMN mimirdata.spans.content IS 'Denormalized copy of selected text for convenience';
COMMENT ON COLUMN mimirdata.spans.annotation IS 'User annotation or note about this span';
