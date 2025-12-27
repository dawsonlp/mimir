-- Migration 001 DOWN: Drop tenants table

DROP TABLE IF EXISTS mimirdata.tenants CASCADE;
DROP TYPE IF EXISTS mimirdata.tenant_type CASCADE;
