-- Migration 002 DOWN: Drop artifacts and artifact_versions tables

DROP TRIGGER IF EXISTS trg_artifacts_updated_at ON mimirdata.artifacts;
DROP FUNCTION IF EXISTS mimirdata.update_updated_at();
DROP TABLE IF EXISTS mimirdata.artifact_versions CASCADE;
DROP TABLE IF EXISTS mimirdata.artifacts CASCADE;
DROP TYPE IF EXISTS mimirdata.artifact_type CASCADE;
