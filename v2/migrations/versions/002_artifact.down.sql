-- Mímir V2 Migration 002: Rollback Artifact and Artifact Version

DROP TRIGGER IF EXISTS artifact_updated_at ON mimirdata.artifact;
DROP FUNCTION IF EXISTS mimirdata.update_updated_at();
DROP TABLE IF EXISTS mimirdata.artifact_version;
DROP TABLE IF EXISTS mimirdata.artifact;
