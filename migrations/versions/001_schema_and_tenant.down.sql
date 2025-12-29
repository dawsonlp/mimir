-- Mímir V2 Migration 001: Rollback Schema, Vocabulary Tables, and Tenant

DROP TABLE IF EXISTS mimirdata.tenant;

DROP TYPE IF EXISTS mimirdata.provenance_actor_type;
DROP TYPE IF EXISTS mimirdata.provenance_action;
DROP TYPE IF EXISTS mimirdata.entity_type;

DROP TABLE IF EXISTS mimirdata.tenant_type;
DROP TABLE IF EXISTS mimirdata.relation_type;
DROP TABLE IF EXISTS mimirdata.artifact_type;
