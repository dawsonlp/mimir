-- Migration 003 Down: Drop intent_groups and intents tables

-- Drop triggers
DROP TRIGGER IF EXISTS trg_intents_updated_at ON mimirdata.intents;
DROP TRIGGER IF EXISTS trg_intent_groups_updated_at ON mimirdata.intent_groups;

-- Drop tables (intents first due to FK dependency)
DROP TABLE IF EXISTS mimirdata.intents;
DROP TABLE IF EXISTS mimirdata.intent_groups;

-- Drop enums
DROP TYPE IF EXISTS mimirdata.intent_source;
DROP TYPE IF EXISTS mimirdata.intent_status;
