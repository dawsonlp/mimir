-- Migration 008 (down): Remove provenance tracking

-- Drop table first (depends on enum types)
DROP TABLE IF EXISTS mimirdata.provenance_events;

-- Drop enum types
DROP TYPE IF EXISTS mimirdata.provenance_actor_type;
DROP TYPE IF EXISTS mimirdata.provenance_action;
DROP TYPE IF EXISTS mimirdata.provenance_entity_type;
