-- Mímir V2 Migration 002: Rollback Artifact and Artifact Version
-- Drops tables and functions in reverse order of creation

-- Drop triggers first
DROP TRIGGER IF EXISTS trigger_artifact_version_search ON mimirdata.artifact_version;
DROP TRIGGER IF EXISTS trigger_artifact_search_vector ON mimirdata.artifact;

-- Drop functions
DROP FUNCTION IF EXISTS mimirdata.update_artifact_from_version();
DROP FUNCTION IF EXISTS mimirdata.update_artifact_search_vector();

-- Drop tables (artifact_version depends on artifact)
DROP TABLE IF EXISTS mimirdata.artifact_version;
DROP TABLE IF EXISTS mimirdata.artifact;
