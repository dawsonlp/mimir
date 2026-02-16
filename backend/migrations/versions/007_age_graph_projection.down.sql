-- Mímir Migration 007 DOWN: Remove AGE Graph Projection
-- Drops all triggers, functions, and tenant graphs
-- No relational data is affected

-- Load AGE into the session
LOAD 'age';
SET search_path = ag_catalog, mimirdata, public;

-- =============================================================================
-- PHASE 1: DROP TRIGGERS
-- =============================================================================

DROP TRIGGER IF EXISTS age_relation_delete_edge ON mimirdata.relation;
DROP TRIGGER IF EXISTS age_relation_create_edge ON mimirdata.relation;
DROP TRIGGER IF EXISTS age_artifact_delete_vertex ON mimirdata.artifact;
DROP TRIGGER IF EXISTS age_artifact_soft_delete_vertex ON mimirdata.artifact;
DROP TRIGGER IF EXISTS age_artifact_create_vertex ON mimirdata.artifact;
DROP TRIGGER IF EXISTS age_tenant_create_graph ON mimirdata.tenant;

-- =============================================================================
-- PHASE 2: DROP TRIGGER FUNCTIONS
-- =============================================================================

DROP FUNCTION IF EXISTS mimirdata.trg_relation_delete_edge();
DROP FUNCTION IF EXISTS mimirdata.trg_relation_create_edge();
DROP FUNCTION IF EXISTS mimirdata.trg_artifact_delete_vertex();
DROP FUNCTION IF EXISTS mimirdata.trg_artifact_soft_delete_vertex();
DROP FUNCTION IF EXISTS mimirdata.trg_artifact_create_vertex();
DROP FUNCTION IF EXISTS mimirdata.trg_tenant_create_graph();

-- =============================================================================
-- PHASE 3: DROP ALL TENANT GRAPHS
-- =============================================================================

DO $$
DECLARE
    v_tenant RECORD;
BEGIN
    FOR v_tenant IN SELECT id FROM mimirdata.tenant LOOP
        PERFORM mimirdata.drop_tenant_graph(v_tenant.id);
    END LOOP;
END;
$$;

-- =============================================================================
-- PHASE 4: DROP HELPER FUNCTIONS
-- =============================================================================

DROP FUNCTION IF EXISTS mimirdata.rebuild_tenant_graph(INT);
DROP FUNCTION IF EXISTS mimirdata.cypher_escape(TEXT);
DROP FUNCTION IF EXISTS mimirdata.drop_tenant_graph(INT);
DROP FUNCTION IF EXISTS mimirdata.create_tenant_graph(INT);
