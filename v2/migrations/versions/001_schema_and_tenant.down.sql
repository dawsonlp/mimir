-- Mímir V2 Migration 001: Rollback Schema and Tenant
-- Drops tenant table and all enums (reverse order of creation)

-- Drop table first (depends on enums)
DROP TABLE IF EXISTS mimirdata.tenant;

-- Drop enums in reverse order
DROP TYPE IF EXISTS mimirdata.provenance_actor_type;
DROP TYPE IF EXISTS mimirdata.provenance_action;
DROP TYPE IF EXISTS mimirdata.span_type;
DROP TYPE IF EXISTS mimirdata.relation_type;
DROP TYPE IF EXISTS mimirdata.entity_type;
DROP TYPE IF EXISTS mimirdata.artifact_type;
DROP TYPE IF EXISTS mimirdata.tenant_type;

-- Note: We do NOT drop the mimirdata schema here because:
-- 1. It may have been created by init-scripts (before migrations)
-- 2. Other tables or the schema_migrations table may exist in it
-- 3. Dropping schema would lose migration tracking
