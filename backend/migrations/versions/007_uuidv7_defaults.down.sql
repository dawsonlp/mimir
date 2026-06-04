-- Mimir Migration 007 DOWN: Restore random UUID defaults

ALTER TABLE mimirdata.artifact
    ALTER COLUMN id SET DEFAULT gen_random_uuid();

ALTER TABLE mimirdata.relation
    ALTER COLUMN id SET DEFAULT gen_random_uuid();

ALTER TABLE mimirdata.embedding
    ALTER COLUMN id SET DEFAULT gen_random_uuid();

ALTER TABLE mimirdata.provenance_event
    ALTER COLUMN id SET DEFAULT gen_random_uuid();

COMMENT ON COLUMN mimirdata.artifact.id IS 'UUID primary key - client-generated UUIDv7 preferred, or server gen_random_uuid()';
