-- Initialize PostgreSQL extensions and schema for Mímir
-- This script runs automatically on first database initialization

-- Create dedicated schema for Mímir data (keeps it isolated from public schema)
CREATE SCHEMA IF NOT EXISTS mimirdata;

-- Set search path to include mimirdata schema
ALTER DATABASE mimir SET search_path TO mimirdata, public;

-- pgvector: Vector similarity search for embeddings
CREATE EXTENSION IF NOT EXISTS vector SCHEMA mimirdata;

-- pg_trgm: Trigram-based fuzzy text search (optional but useful)
CREATE EXTENSION IF NOT EXISTS pg_trgm;
