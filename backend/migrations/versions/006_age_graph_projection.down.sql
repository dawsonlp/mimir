-- Migration 006 DOWN: Remove Apache AGE Graph Projection

-- Drop triggers first
DROP TRIGGER IF EXISTS age_relation_delete_edge ON mimirdata.relation;
DROP TRIGGER IF EXISTS age_relation_create_edge ON mimirdata.relation;
DROP TRIGGER IF EXISTS age_artifact_delete_vertex ON mimirdata.artifact;
DROP TRIGGER IF EXISTS age_artifact_create_vertex ON mimirdata.artifact;
DROP TRIGGER IF EXISTS age_tenant_create_graph ON mimirdata.tenant;

-- Drop trigger functions
DROP FUNCTION IF EXISTS mimirdata.trg_relation_delete_edge();
DROP FUNCTION IF EXISTS mimirdata.trg_relation_create_edge();
DROP FUNCTION IF EXISTS mimirdata.trg_artifact_delete_vertex();
DROP FUNCTION IF EXISTS mimirdata.trg_artifact_create_vertex();
DROP FUNCTION IF EXISTS mimirdata.trg_tenant_create_graph();

-- Drop helper functions
DROP FUNCTION IF EXISTS mimirdata.rebuild_tenant_graph(INT);
DROP FUNCTION IF EXISTS mimirdata.cypher_escape(TEXT);
DROP FUNCTION IF EXISTS mimirdata.drop_tenant_graph(INT);
DROP FUNCTION IF EXISTS mimirdata.create_tenant_graph(INT);