-- 006 DOWN: Remove deletion infrastructure
-- Reverses: deletion_policy on tenant_type, deleted_at on artifact

DROP INDEX IF EXISTS mimirdata.idx_artifact_deleted;
ALTER TABLE mimirdata.artifact DROP COLUMN IF EXISTS deleted_at;
ALTER TABLE mimirdata.tenant_type DROP COLUMN IF EXISTS deletion_policy;