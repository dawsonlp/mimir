-- Mimir Migration 008 DOWN: Drop Change Outbox

DROP TABLE IF EXISTS mimirdata.change_outbox CASCADE;
