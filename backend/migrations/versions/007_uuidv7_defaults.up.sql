-- Mimir Migration 007: UUIDv7 defaults
-- Ensure server/database-generated UUIDs use UUIDv7 on existing databases.

ALTER TABLE mimirdata.artifact
    ALTER COLUMN id SET DEFAULT uuidv7();

ALTER TABLE mimirdata.relation
    ALTER COLUMN id SET DEFAULT uuidv7();

ALTER TABLE mimirdata.embedding
    ALTER COLUMN id SET DEFAULT uuidv7();

ALTER TABLE mimirdata.provenance_event
    ALTER COLUMN id SET DEFAULT uuidv7();

COMMENT ON COLUMN mimirdata.artifact.id IS 'UUIDv7 primary key - client-generated preferred, or server uuidv7()';
