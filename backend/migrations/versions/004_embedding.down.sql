-- Mímir V2 Migration 004: Embedding (Down)
-- Drops embedding tables and mimir_vectors schema

-- Drop embedding metadata table (cascades to vector table references)
DROP TABLE IF EXISTS mimirdata.embedding CASCADE;

-- Drop embedding type vocabulary table
DROP TABLE IF EXISTS mimirdata.embedding_type CASCADE;

-- Drop all vector tables and the schema
-- CASCADE handles all tables within the schema
DROP SCHEMA IF EXISTS mimir_vectors CASCADE;