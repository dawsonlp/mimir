-- Migration 006 DOWN: Drop relations table

DROP TRIGGER IF EXISTS trg_relations_updated_at ON mimirdata.relations;
DROP TABLE IF EXISTS mimirdata.relations;
DROP TYPE IF EXISTS mimirdata.relation_type;
DROP TYPE IF EXISTS mimirdata.entity_type;
