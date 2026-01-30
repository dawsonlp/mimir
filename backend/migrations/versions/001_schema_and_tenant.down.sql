-- Mímir V2 Migration 001 DOWN: Drop schema, vocabulary tables, and tenant
DROP TABLE IF EXISTS mimirdata.tenant CASCADE;
DROP TABLE IF EXISTS mimirdata.relation_type CASCADE;
DROP TABLE IF EXISTS mimirdata.artifact_type CASCADE;
DROP TABLE IF EXISTS mimirdata.tenant_type CASCADE;
DROP SCHEMA IF EXISTS mimirdata CASCADE;
