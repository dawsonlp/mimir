-- 006: Deletion infrastructure — tenant-type-scoped deletion policy and soft-delete column
-- Depends on: 001 (tenant_type, tenant), 002 (artifact)
--
-- Phase 2 of the Enhancement Roadmap:
--   - Add deletion_policy column to tenant_type vocabulary table
--   - Seed deletion policies per tenant type
--   - Add deleted_at column to artifact table for soft-delete support
--   - Add partial index on deleted_at for efficient filtering

-- ── Tenant type deletion policy ─────────────────────────────────────────
-- This is a vocabulary/admin table (mutable), so adding a column does NOT
-- violate the append-only invariant on content tables.
ALTER TABLE mimirdata.tenant_type
    ADD COLUMN deletion_policy TEXT NOT NULL DEFAULT 'soft_delete';

-- Set deletion policies per tenant type
-- environment → soft_delete (standard: logically removed, audit preserved)
-- project     → no_delete   (audited: append-only invariant strictly enforced)
-- experiment  → physical_delete (sandbox: physical removal permitted)
UPDATE mimirdata.tenant_type SET deletion_policy = 'soft_delete'      WHERE code = 'environment';
UPDATE mimirdata.tenant_type SET deletion_policy = 'no_delete'        WHERE code = 'project';
UPDATE mimirdata.tenant_type SET deletion_policy = 'physical_delete'  WHERE code = 'experiment';

-- ── Artifact soft-delete column ─────────────────────────────────────────
-- NULL means active (not deleted). Non-NULL means soft-deleted at that timestamp.
ALTER TABLE mimirdata.artifact
    ADD COLUMN deleted_at TIMESTAMPTZ NULL;

-- Partial index: only indexes rows that ARE soft-deleted.
-- Queries filtering active artifacts (deleted_at IS NULL) benefit from the
-- default table scan excluding the indexed subset. Queries finding deleted
-- artifacts use this index directly.
CREATE INDEX idx_artifact_deleted
    ON mimirdata.artifact (deleted_at)
    WHERE deleted_at IS NOT NULL;