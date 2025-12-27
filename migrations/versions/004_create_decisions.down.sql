-- Migration 004 Down: Drop decisions table

-- Drop trigger
DROP TRIGGER IF EXISTS trg_decisions_updated_at ON mimirdata.decisions;

-- Drop table
DROP TABLE IF EXISTS mimirdata.decisions;

-- Drop enums
DROP TYPE IF EXISTS mimirdata.decision_source;
DROP TYPE IF EXISTS mimirdata.decision_status;
