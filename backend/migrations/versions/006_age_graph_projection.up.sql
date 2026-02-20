-- Mímir Migration 006: AGE Graph Projection
-- Projects relational artifacts/relations into per-tenant AGE graphs
-- See: docs/age-graph-projection-technical-design.md
--
-- Requires: Apache AGE extension (already created by init-scripts)

-- =============================================================================
-- PHASE 1: HELPER FUNCTIONS
-- =============================================================================

-- Load AGE into the session for this migration
LOAD 'age';
SET search_path = ag_catalog, mimirdata, public;

-- -----------------------------------------------------------------------------
-- create_tenant_graph: Create an AGE graph for a tenant with labels
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION mimirdata.create_tenant_graph(p_tenant_id INT)
RETURNS void AS $$
DECLARE
    v_graph_name TEXT := 'mimir_tenant_' || p_tenant_id::text;
BEGIN
    -- Create the graph
    PERFORM ag_catalog.create_graph(v_graph_name);

    -- Create vertex label via placeholder (Cypher auto-creates labels on first use)
    EXECUTE format(
        'SELECT * FROM ag_catalog.cypher(%L, $cypher$
            CREATE (n:Artifact {_init: true})
            RETURN n
        $cypher$) AS (v ag_catalog.agtype)',
        v_graph_name
    );
    EXECUTE format(
        'SELECT * FROM ag_catalog.cypher(%L, $cypher$
            MATCH (n:Artifact {_init: true})
            DELETE n
        $cypher$) AS (v ag_catalog.agtype)',
        v_graph_name
    );

    -- Create edge label via placeholder
    EXECUTE format(
        'SELECT * FROM ag_catalog.cypher(%L, $cypher$
            CREATE (a:Artifact {_init_s: true})-[:Relation {_init: true}]->(b:Artifact {_init_t: true})
            RETURN a
        $cypher$) AS (v ag_catalog.agtype)',
        v_graph_name
    );
    EXECUTE format(
        'SELECT * FROM ag_catalog.cypher(%L, $cypher$
            MATCH (a:Artifact {_init_s: true})-[r:Relation]->(b:Artifact {_init_t: true})
            DELETE r, a, b
        $cypher$) AS (v ag_catalog.agtype)',
        v_graph_name
    );
END;
$$ LANGUAGE plpgsql;

-- -----------------------------------------------------------------------------
-- drop_tenant_graph: Drop a tenant's AGE graph if it exists
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION mimirdata.drop_tenant_graph(p_tenant_id INT)
RETURNS void AS $$
DECLARE
    v_graph_name TEXT := 'mimir_tenant_' || p_tenant_id::text;
    v_exists BOOLEAN;
BEGIN
    SELECT EXISTS(
        SELECT 1 FROM ag_catalog.ag_graph WHERE name = v_graph_name
    ) INTO v_exists;

    IF v_exists THEN
        PERFORM ag_catalog.drop_graph(v_graph_name, true);
    END IF;
END;
$$ LANGUAGE plpgsql;

-- -----------------------------------------------------------------------------
-- Helper: Escape a text value for embedding in Cypher string literals
-- Replaces backslash and single-quote to prevent injection
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION mimirdata.cypher_escape(val TEXT)
RETURNS TEXT AS $$
BEGIN
    IF val IS NULL THEN
        RETURN '';
    END IF;
    RETURN replace(replace(val, '\', '\\'), '''', '\''');
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- -----------------------------------------------------------------------------
-- rebuild_tenant_graph: Full rebuild from relational data
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION mimirdata.rebuild_tenant_graph(p_tenant_id INT)
RETURNS void AS $$
DECLARE
    v_graph_name TEXT := 'mimir_tenant_' || p_tenant_id::text;
    v_cypher TEXT;
    rec RECORD;
BEGIN
    -- Drop and recreate
    PERFORM mimirdata.drop_tenant_graph(p_tenant_id);
    PERFORM mimirdata.create_tenant_graph(p_tenant_id);

    -- Bulk insert all artifacts as vertices
    FOR rec IN
        SELECT id, artifact_type, title, created_at
        FROM mimirdata.artifact
        WHERE tenant_id = p_tenant_id
    LOOP
        v_cypher := format(
            'SELECT * FROM ag_catalog.cypher(%L, $cypher$
                CREATE (:Artifact {
                    mimir_id: %s,
                    artifact_type: %s,
                    title: %s,
                    created_at: %s
                })
            $cypher$) AS (v ag_catalog.agtype)',
            v_graph_name,
            quote_literal(rec.id::text),
            quote_literal(rec.artifact_type),
            quote_literal(mimirdata.cypher_escape(COALESCE(rec.title, ''))),
            quote_literal(rec.created_at::text)
        );
        EXECUTE v_cypher;
    END LOOP;

    -- Bulk insert all relations as edges
    FOR rec IN
        SELECT r.id, r.source_id, r.target_id, r.relation_type,
               r.confidence, r.created_at
        FROM mimirdata.relation r
        WHERE r.tenant_id = p_tenant_id
    LOOP
        v_cypher := format(
            'SELECT * FROM ag_catalog.cypher(%L, $cypher$
                MATCH (s:Artifact {mimir_id: %s}), (t:Artifact {mimir_id: %s})
                CREATE (s)-[:Relation {
                    mimir_id: %s,
                    relation_type: %s,
                    confidence: %s,
                    created_at: %s
                }]->(t)
            $cypher$) AS (e ag_catalog.agtype)',
            v_graph_name,
            quote_literal(rec.source_id::text),
            quote_literal(rec.target_id::text),
            quote_literal(rec.id::text),
            quote_literal(rec.relation_type),
            COALESCE(rec.confidence, 0.0)::text,
            quote_literal(rec.created_at::text)
        );
        EXECUTE v_cypher;
    END LOOP;
END;
$$ LANGUAGE plpgsql;


-- =============================================================================
-- PHASE 2: TRIGGER FUNCTIONS
-- =============================================================================

-- -----------------------------------------------------------------------------
-- Tenant: AFTER INSERT → create graph
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION mimirdata.trg_tenant_create_graph()
RETURNS trigger AS $$
BEGIN
    PERFORM mimirdata.create_tenant_graph(NEW.id);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- -----------------------------------------------------------------------------
-- Artifact: AFTER INSERT → create vertex
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION mimirdata.trg_artifact_create_vertex()
RETURNS trigger AS $$
DECLARE
    v_graph_name TEXT := 'mimir_tenant_' || NEW.tenant_id::text;
    v_cypher TEXT;
BEGIN
    v_cypher := format(
        'SELECT * FROM ag_catalog.cypher(%L, $cypher$
            CREATE (:Artifact {
                mimir_id: %s,
                artifact_type: %s,
                title: %s,
                created_at: %s
            })
        $cypher$) AS (v ag_catalog.agtype)',
        v_graph_name,
        quote_literal(NEW.id::text),
        quote_literal(NEW.artifact_type),
        quote_literal(mimirdata.cypher_escape(COALESCE(NEW.title, ''))),
        quote_literal(NEW.created_at::text)
    );
    EXECUTE v_cypher;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- -----------------------------------------------------------------------------
-- Artifact: AFTER DELETE → remove vertex on physical delete
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION mimirdata.trg_artifact_delete_vertex()
RETURNS trigger AS $$
DECLARE
    v_graph_name TEXT := 'mimir_tenant_' || OLD.tenant_id::text;
    v_cypher TEXT;
BEGIN
    v_cypher := format(
        'SELECT * FROM ag_catalog.cypher(%L, $cypher$
            MATCH (a:Artifact {mimir_id: %s})
            DETACH DELETE a
        $cypher$) AS (v ag_catalog.agtype)',
        v_graph_name,
        quote_literal(OLD.id::text)
    );
    EXECUTE v_cypher;

    RETURN OLD;
END;
$$ LANGUAGE plpgsql;

-- -----------------------------------------------------------------------------
-- Relation: AFTER INSERT → create edge
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION mimirdata.trg_relation_create_edge()
RETURNS trigger AS $$
DECLARE
    v_graph_name TEXT := 'mimir_tenant_' || NEW.tenant_id::text;
    v_cypher TEXT;
BEGIN
    v_cypher := format(
        'SELECT * FROM ag_catalog.cypher(%L, $cypher$
            MATCH (s:Artifact {mimir_id: %s}), (t:Artifact {mimir_id: %s})
            CREATE (s)-[:Relation {
                mimir_id: %s,
                relation_type: %s,
                confidence: %s,
                created_at: %s
            }]->(t)
        $cypher$) AS (e ag_catalog.agtype)',
        v_graph_name,
        quote_literal(NEW.source_id::text),
        quote_literal(NEW.target_id::text),
        quote_literal(NEW.id::text),
        quote_literal(NEW.relation_type),
        COALESCE(NEW.confidence, 0.0)::text,
        quote_literal(NEW.created_at::text)
    );
    EXECUTE v_cypher;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- -----------------------------------------------------------------------------
-- Relation: AFTER DELETE → remove edge on physical delete
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION mimirdata.trg_relation_delete_edge()
RETURNS trigger AS $$
DECLARE
    v_graph_name TEXT := 'mimir_tenant_' || OLD.tenant_id::text;
    v_cypher TEXT;
BEGIN
    v_cypher := format(
        'SELECT * FROM ag_catalog.cypher(%L, $cypher$
            MATCH (s:Artifact {mimir_id: %s})-[r:Relation {mimir_id: %s}]->(t:Artifact {mimir_id: %s})
            DELETE r
        $cypher$) AS (e ag_catalog.agtype)',
        v_graph_name,
        quote_literal(OLD.source_id::text),
        quote_literal(OLD.id::text),
        quote_literal(OLD.target_id::text)
    );
    EXECUTE v_cypher;

    RETURN OLD;
END;
$$ LANGUAGE plpgsql;


-- =============================================================================
-- PHASE 3: ATTACH TRIGGERS
-- =============================================================================

-- Tenant triggers
CREATE TRIGGER age_tenant_create_graph
    AFTER INSERT ON mimirdata.tenant
    FOR EACH ROW
    EXECUTE FUNCTION mimirdata.trg_tenant_create_graph();

-- Artifact triggers
CREATE TRIGGER age_artifact_create_vertex
    AFTER INSERT ON mimirdata.artifact
    FOR EACH ROW
    EXECUTE FUNCTION mimirdata.trg_artifact_create_vertex();

CREATE TRIGGER age_artifact_delete_vertex
    AFTER DELETE ON mimirdata.artifact
    FOR EACH ROW
    EXECUTE FUNCTION mimirdata.trg_artifact_delete_vertex();

-- Relation triggers
CREATE TRIGGER age_relation_create_edge
    AFTER INSERT ON mimirdata.relation
    FOR EACH ROW
    EXECUTE FUNCTION mimirdata.trg_relation_create_edge();

CREATE TRIGGER age_relation_delete_edge
    AFTER DELETE ON mimirdata.relation
    FOR EACH ROW
    EXECUTE FUNCTION mimirdata.trg_relation_delete_edge();


-- =============================================================================
-- PHASE 4: BOOTSTRAP EXISTING DATA
-- =============================================================================

DO $$
DECLARE
    v_tenant RECORD;
BEGIN
    FOR v_tenant IN SELECT id FROM mimirdata.tenant LOOP
        PERFORM mimirdata.rebuild_tenant_graph(v_tenant.id);
    END LOOP;
END;
$$;