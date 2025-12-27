-- Migration 001: Create tenants table
-- Multi-tenant support for data segmentation by environment/project

-- Tenant type enum
CREATE TYPE mimirdata.tenant_type AS ENUM (
    'environment',  -- dev, staging, production
    'project',      -- systems_architecture, billing, etc.
    'experiment'    -- A/B tests, feature flags
);

-- Tenants table
CREATE TABLE mimirdata.tenants (
    id SERIAL PRIMARY KEY,
    shortname TEXT NOT NULL UNIQUE,  -- e.g., 'development', 'systems_architecture'
    name TEXT NOT NULL,              -- Display name
    tenant_type mimirdata.tenant_type NOT NULL DEFAULT 'project',
    description TEXT,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

-- Index for active tenant lookups
CREATE INDEX idx_tenants_active ON mimirdata.tenants (is_active) WHERE is_active = true;

-- Index for shortname lookups (unique constraint handles this but explicit index is clearer)
CREATE INDEX idx_tenants_shortname ON mimirdata.tenants (shortname);

-- Comments for documentation
COMMENT ON TABLE mimirdata.tenants IS 'Multi-tenant support for data segmentation';
COMMENT ON COLUMN mimirdata.tenants.shortname IS 'URL-safe unique identifier';
COMMENT ON COLUMN mimirdata.tenants.tenant_type IS 'Categorization: environment, project, or experiment';
COMMENT ON COLUMN mimirdata.tenants.metadata IS 'Extensible properties as JSONB';

-- Insert default tenant for development
INSERT INTO mimirdata.tenants (shortname, name, tenant_type, description) VALUES
    ('default', 'Default Tenant', 'environment', 'Default tenant for development and testing');
