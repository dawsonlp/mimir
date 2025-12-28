-- Migration 009: Add Ollama embedding models to enum
-- Extends the embedding_model enum to support Ollama local models

-- Add Ollama models to the enum
ALTER TYPE mimirdata.embedding_model ADD VALUE IF NOT EXISTS 'nomic-embed-text';
ALTER TYPE mimirdata.embedding_model ADD VALUE IF NOT EXISTS 'mxbai-embed-large';
ALTER TYPE mimirdata.embedding_model ADD VALUE IF NOT EXISTS 'snowflake-arctic-embed';
ALTER TYPE mimirdata.embedding_model ADD VALUE IF NOT EXISTS 'all-minilm';
ALTER TYPE mimirdata.embedding_model ADD VALUE IF NOT EXISTS 'bge-large';
ALTER TYPE mimirdata.embedding_model ADD VALUE IF NOT EXISTS 'bge-base';

-- Also add Voyage AI models that may have been missed
ALTER TYPE mimirdata.embedding_model ADD VALUE IF NOT EXISTS 'voyage-3';
ALTER TYPE mimirdata.embedding_model ADD VALUE IF NOT EXISTS 'voyage-3-lite';
ALTER TYPE mimirdata.embedding_model ADD VALUE IF NOT EXISTS 'voyage-code-3';
ALTER TYPE mimirdata.embedding_model ADD VALUE IF NOT EXISTS 'voyage-finance-2';
ALTER TYPE mimirdata.embedding_model ADD VALUE IF NOT EXISTS 'voyage-law-2';
ALTER TYPE mimirdata.embedding_model ADD VALUE IF NOT EXISTS 'voyage-code-2';

COMMENT ON TYPE mimirdata.embedding_model IS 'Supported embedding models (OpenAI, Voyage AI, Ollama)';
