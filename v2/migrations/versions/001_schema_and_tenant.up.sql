-- Mímir V2 Migration 001: Schema, Vocabulary Tables, and Tenant
-- Creates mimirdata schema, vocabulary tables, system enums, and tenant table

-- =============================================================================
-- SCHEMA
-- =============================================================================
-- Schema created by init-scripts/01-create-extensions.sql, but ensure it exists
CREATE SCHEMA IF NOT EXISTS mimirdata;

-- =============================================================================
-- VOCABULARY TABLES (extensible via data, not schema)
-- =============================================================================

-- Artifact Type vocabulary
CREATE TABLE mimirdata.artifact_type (
    code TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    description TEXT,
    category TEXT,                       -- Grouping: 'content', 'positional', 'derived'
    is_active BOOLEAN NOT NULL DEFAULT true,
    sort_order INT DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Seed artifact types
INSERT INTO mimirdata.artifact_type (code, display_name, description, category, sort_order) VALUES
    -- Raw content
    ('conversation', 'Conversation', 'A conversation or chat thread', 'content', 10),
    ('document', 'Document', 'A document or file', 'content', 20),
    ('note', 'Note', 'A user note or annotation', 'content', 30),
    -- Positional extractions (chunks within content)
    ('chunk', 'Chunk', 'A chunk of content for embedding', 'positional', 100),
    ('quote', 'Quote', 'An exact quote from source', 'positional', 110),
    ('highlight', 'Highlight', 'A highlighted section', 'positional', 120),
    ('annotation', 'Annotation', 'An annotation on content', 'positional', 130),
    ('reference', 'Reference', 'A reference to external content', 'positional', 140),
    ('bookmark', 'Bookmark', 'A bookmark to a position', 'positional', 150),
    -- Derived knowledge
    ('intent', 'Intent', 'A captured intent or goal', 'derived', 200),
    ('intent_group', 'Intent Group', 'A grouping of related intents', 'derived', 210),
    ('decision', 'Decision', 'A decision with rationale', 'derived', 220),
    ('analysis', 'Analysis', 'An analysis of content', 'derived', 230),
    ('summary', 'Summary', 'A summary of content', 'derived', 240),
    ('conclusion', 'Conclusion', 'A conclusion drawn from evidence', 'derived', 250),
    ('finding', 'Finding', 'A finding or discovery', 'derived', 260),
    ('question', 'Question', 'A question for exploration', 'derived', 270),
    ('answer', 'Answer', 'An answer to a question', 'derived', 280);

COMMENT ON TABLE mimirdata.artifact_type IS 'Vocabulary table for artifact types - extensible via INSERT';

-- Relation Type vocabulary
CREATE TABLE mimirdata.relation_type (
    code TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    description TEXT,
    inverse_code TEXT,                   -- Optional: code of inverse relation
    is_symmetric BOOLEAN DEFAULT false,  -- true if A→B implies B→A
    is_active BOOLEAN NOT NULL DEFAULT true,
    sort_order INT DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Seed relation types
INSERT INTO mimirdata.relation_type (code, display_name, description, inverse_code, is_symmetric, sort_order) VALUES
    ('references', 'References', 'Source references target', 'referenced_by', false, 10),
    ('referenced_by', 'Referenced By', 'Target is referenced by source', 'references', false, 11),
    ('supports', 'Supports', 'Source supports target claim', 'supported_by', false, 20),
    ('supported_by', 'Supported By', 'Target is supported by source', 'supports', false, 21),
    ('contradicts', 'Contradicts', 'Source contradicts target', NULL, true, 30),
    ('derived_from', 'Derived From', 'Source was derived from target', 'source_of', false, 40),
    ('source_of', 'Source Of', 'Source is origin of target', 'derived_from', false, 41),
    ('supersedes', 'Supersedes', 'Source supersedes/replaces target', 'superseded_by', false, 50),
    ('superseded_by', 'Superseded By', 'Source was replaced by target', 'supersedes', false, 51),
    ('related_to', 'Related To', 'General relationship', NULL, true, 60),
    ('parent_of', 'Parent Of', 'Source is parent of target', 'child_of', false, 70),
    ('child_of', 'Child Of', 'Source is child of target', 'parent_of', false, 71),
    ('implements', 'Implements', 'Source implements target intent/decision', 'implemented_by', false, 80),
    ('implemented_by', 'Implemented By', 'Target is implementation of source', 'implements', false, 81),
    ('resolves', 'Resolves', 'Source resolves target question', 'resolved_by', false, 90),
    ('resolved_by', 'Resolved By', 'Target is resolved by source', 'resolves', false, 91);

COMMENT ON TABLE mimirdata.relation_type IS 'Vocabulary table for relation types - includes inverse relationship support';

-- Tenant Type vocabulary
CREATE TABLE mimirdata.tenant_type (
    code TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    description TEXT,
    is_active BOOLEAN NOT NULL DEFAULT true,
    sort_order INT DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Seed tenant types
INSERT INTO mimirdata.tenant_type (code, display_name, description, sort_order) VALUES
    ('environment', 'Environment', 'A general purpose environment', 10),
    ('project', 'Project', 'A project workspace', 20),
    ('experiment', 'Experiment', 'An experimental workspace', 30);

COMMENT ON TABLE mimirdata.tenant_type IS 'Vocabulary table for tenant types';

-- =============================================================================
-- SYSTEM ENUMS (fixed, rarely change)
-- =============================================================================

-- Entity types for relations (truly fixed - only these can be related)
CREATE TYPE mimirdata.entity_type AS ENUM (
    'artifact',
    'artifact_version'
);

-- Provenance action types (system events)
CREATE TYPE mimirdata.provenance_action AS ENUM (
    'create',
    'update',
    'delete',
    'supersede',
    'archive',
    'restore'
);

-- Provenance actor types (system categories)
CREATE TYPE mimirdata.provenance_actor_type AS ENUM (
    'user',
    'system',
    'llm',
    'api_client',
    'migration'
);

-- =============================================================================
-- TENANT TABLE
-- =============================================================================

CREATE TABLE mimirdata.tenant (
    id SERIAL PRIMARY KEY,
    shortname TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    tenant_type TEXT NOT NULL DEFAULT 'environment' REFERENCES mimirdata.tenant_type(code),
    description TEXT,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata JSONB DEFAULT '{}'::jsonb
);

CREATE INDEX idx_tenant_shortname ON mimirdata.tenant (shortname);
CREATE INDEX idx_tenant_type ON mimirdata.tenant (tenant_type);
CREATE INDEX idx_tenant_active ON mimirdata.tenant (is_active) WHERE is_active = true;

COMMENT ON TABLE mimirdata.tenant IS 'Multi-tenant isolation - each tenant is a logical partition';
