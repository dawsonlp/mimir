-- Rollback Migration 010: Remove source_system column

-- Drop indexes
DROP INDEX IF EXISTS mimirdata.idx_artifacts_source_system_external_id;
DROP INDEX IF EXISTS mimirdata.idx_artifacts_source_system;

-- Remove column
ALTER TABLE mimirdata.artifacts
DROP COLUMN IF EXISTS source_system;
