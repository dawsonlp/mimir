-- Mímir V2 Migration 001: Schema and Tenant
-- Creates mimirdata schema, all enums, and tenant table

-- Ensure schema exists (idempotent - init script may have already created it)
CREATE SCHEMA IF NOT EXISTS mimirdata;

-- =============================================================================
-- ENUMS - All defined from the start for V2 clean design
-- =============================================================================

-- Tenant type - categorizes the purpose of a tenant
CREATE TYPE mimirdata.tenant_type AS ENUM (
    'environment',   -- dev, staging, prod
    'project',       -- project-based isolation
    'experiment'     -- experimental/temporary
);

-- Artifact type - extended to include derived knowledge types
CREATE TYPE mimirdata.artifact_type AS ENUM (
    -- Raw content types
    'conversation',  -- chat conversations
    'document',      -- documents, files
    'note',          -- freeform notes
    'chunk',         -- chunked content for processing
    -- Derived knowledge types (V2 unified model)
    'intent',        -- what the user wants to accomplish
    'decision',      -- decision that was made
    'analysis',      -- analytical content
    'summary',       -- summarized content
    'conclusion',    -- conclusions drawn
    'finding',       -- discoveries/findings
    'question',      -- questions asked
    'answer'         -- answers provided
);

-- Entity type - simplified for V2 (only 3 types)
CREATE TYPE mimirdata.entity_type AS ENUM (
    'artifact',          -- main content entities
    'artifact_version',  -- versioned content
    'span'               -- positional annotations
);

-- Relation type - how entities connect
CREATE TYPE mimirdata.relation_type AS ENUM (
    'references',    -- points to another entity
    'supports',      -- provides evidence for
    'contradicts',   -- conflicts with
    'derived_from',  -- was created from
    'supersedes',    -- replaces an older entity
    'related_to',    -- general relationship
    'parent_of',     -- hierarchical parent
    'child_of',      -- hierarchical child
    'implements',    -- implements/fulfills
    'resolves'       -- resolves/addresses
);

-- Span type - types of positional annotations
CREATE TYPE mimirdata.span_type AS ENUM (
    'quote',         -- quoted text
    'highlight',     -- highlighted section
    'annotation',    -- annotated section
    'reference',     -- reference point
    'bookmark'       -- bookmarked location
);

-- Provenance action type - what happened
CREATE TYPE mimirdata.provenance_action AS ENUM (
    'create',        -- entity was created
    'update',        -- entity was updated
    'delete',        -- entity was deleted
    'supersede',     -- entity was superseded
    'archive',       -- entity was archived
    'restore'        -- entity was restored
);

-- Provenance actor type - who/what performed the action
CREATE TYPE mimirdata.provenance_actor_type AS ENUM (
    'user',          -- human user
    'system',        -- automated system process
    'llm',           -- LLM/AI agent
    'api_client',    -- external API client
    'migration'      -- database migration
);

-- =============================================================================
-- TENANT TABLE
-- =============================================================================

CREATE TABLE mimirdata.tenant (
    id SERIAL PRIMARY KEY,
    shortname TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    tenant_type mimirdata.tenant_type NOT NULL DEFAULT 'project',
    description TEXT,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata JSONB DEFAULT '{}'::jsonb
);

-- Index for active tenant lookups
CREATE INDEX idx_tenant_active ON mimirdata.tenant (is_active) WHERE is_active = true;

-- Index for shortname lookups (unique constraint already creates one, but explicit for clarity)
CREATE INDEX idx_tenant_shortname ON mimirdata.tenant (shortname);

COMMENT ON TABLE mimirdata.tenant IS 'Multi-tenant isolation - each tenant is a logical partition';
COMMENT ON COLUMN mimirdata.tenant.shortname IS 'Unique identifier used in URLs and references';
COMMENT ON COLUMN mimirdata.tenant.tenant_type IS 'Categorization: environment, project, or experiment';
COMMENT ON COLUMN mimirdata.tenant.metadata IS 'Extensible properties as JSONB';
