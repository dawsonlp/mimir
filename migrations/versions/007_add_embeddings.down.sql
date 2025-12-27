-- Migration 007 DOWN: Remove embeddings and full-text search support

-- Remove triggers first
DROP TRIGGER IF EXISTS trg_artifact_versions_search_vector ON mimirdata.artifact_versions;
DROP TRIGGER IF EXISTS trg_artifacts_search_vector ON mimirdata.artifacts;

-- Remove trigger functions
DROP FUNCTION IF EXISTS mimirdata.update_artifact_version_search_vector();
DROP FUNCTION IF EXISTS mimirdata.update_artifact_search_vector();

-- Remove search_vector columns
ALTER TABLE mimirdata.artifact_versions DROP COLUMN IF EXISTS search_vector;
ALTER TABLE mimirdata.artifacts DROP COLUMN IF EXISTS search_vector;

-- Drop embeddings table (indexes dropped automatically)
DROP TABLE IF EXISTS mimirdata.embeddings;

-- Drop embedding model enum
DROP TYPE IF EXISTS mimirdata.embedding_model;
