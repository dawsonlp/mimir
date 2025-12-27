-- Migration 005 DOWN: Drop spans table

DROP TRIGGER IF EXISTS trg_spans_updated_at ON mimirdata.spans;
DROP TABLE IF EXISTS mimirdata.spans;
DROP TYPE IF EXISTS mimirdata.span_type;
