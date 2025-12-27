-- Migration 007: Add embeddings and full-text search support
-- Enables semantic search via pgvector and full-text search via PostgreSQL FTS

-- Embedding model enum (extensible for future models)
CREATE TYPE mimirdata.embedding_model AS ENUM (
    'openai-text-embedding-3-small',   -- 1536 dimensions
    'openai-text-embedding-3-large',   -- 3072 dimensions
    'openai-text-embedding-ada-002',   -- 1536 dimensions (legacy)
    'sentence-transformers-all-mpnet', -- 768 dimensions
    'sentence-transformers-all-minilm' -- 384 dimensions
);

-- Embeddings table (one-to-many with artifacts, allows multiple models)
-- Note: pgvector HNSW index supports max 2000 dimensions
-- Using 1536 dimensions (supports text-embedding-3-small, ada-002, and truncated large model)
CREATE TABLE mimirdata.embeddings (
    id SERIAL PRIMARY KEY,
    tenant_id INT NOT NULL REFERENCES mimirdata.tenants(id) ON DELETE RESTRICT,
    artifact_id INT NOT NULL REFERENCES mimirdata.artifacts(id) ON DELETE CASCADE,
    artifact_version_id INT REFERENCES mimirdata.artifact_versions(id) ON DELETE SET NULL,
    model mimirdata.embedding_model NOT NULL,
    embedding mimirdata.vector(1536) NOT NULL,  -- 1536 dimensions (HNSW max is 2000)
    dimensions INT NOT NULL,                      -- Actual dimensions used
    chunk_index INT NOT NULL DEFAULT 0,           -- For chunked documents (0 = full doc)
    chunk_text TEXT,                              -- Original text chunk (optional, for debugging)
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    
    -- Prevent duplicate embeddings per artifact/model/chunk
    CONSTRAINT uq_embedding UNIQUE (artifact_id, model, chunk_index)
);

-- HNSW index for approximate nearest neighbor search (cosine similarity)
-- m=16: connections per node, ef_construction=64: build-time accuracy
-- Note: HNSW supports max 2000 dimensions; we use 1536 for best model compatibility
CREATE INDEX idx_embeddings_vector_hnsw ON mimirdata.embeddings 
    USING hnsw (embedding mimirdata.vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- Standard indexes
CREATE INDEX idx_embeddings_tenant ON mimirdata.embeddings (tenant_id);
CREATE INDEX idx_embeddings_artifact ON mimirdata.embeddings (artifact_id);
CREATE INDEX idx_embeddings_model ON mimirdata.embeddings (model);
CREATE INDEX idx_embeddings_created_at ON mimirdata.embeddings (created_at DESC);

-- Composite index for tenant-scoped searches
CREATE INDEX idx_embeddings_tenant_model ON mimirdata.embeddings (tenant_id, model);

-- Add full-text search column to artifacts
ALTER TABLE mimirdata.artifacts ADD COLUMN search_vector TSVECTOR;

-- GIN index for full-text search on artifacts
CREATE INDEX idx_artifacts_search_vector ON mimirdata.artifacts USING GIN (search_vector);

-- Add full-text search column to artifact_versions (for content search)
ALTER TABLE mimirdata.artifact_versions ADD COLUMN search_vector TSVECTOR;

-- GIN index for full-text search on artifact_versions
CREATE INDEX idx_artifact_versions_search_vector ON mimirdata.artifact_versions USING GIN (search_vector);

-- Trigger function to update search_vector on artifacts (title + metadata)
CREATE OR REPLACE FUNCTION mimirdata.update_artifact_search_vector()
RETURNS TRIGGER AS $$
BEGIN
    NEW.search_vector = 
        setweight(to_tsvector('english', COALESCE(NEW.title, '')), 'A') ||
        setweight(to_tsvector('english', COALESCE(NEW.metadata::text, '')), 'B');
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_artifacts_search_vector
    BEFORE INSERT OR UPDATE OF title, metadata ON mimirdata.artifacts
    FOR EACH ROW
    EXECUTE FUNCTION mimirdata.update_artifact_search_vector();

-- Trigger function to update search_vector on artifact_versions (content)
CREATE OR REPLACE FUNCTION mimirdata.update_artifact_version_search_vector()
RETURNS TRIGGER AS $$
BEGIN
    NEW.search_vector = to_tsvector('english', COALESCE(NEW.content, ''));
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_artifact_versions_search_vector
    BEFORE INSERT OR UPDATE OF content ON mimirdata.artifact_versions
    FOR EACH ROW
    EXECUTE FUNCTION mimirdata.update_artifact_version_search_vector();

-- Backfill existing artifacts search_vector
UPDATE mimirdata.artifacts SET 
    search_vector = 
        setweight(to_tsvector('english', COALESCE(title, '')), 'A') ||
        setweight(to_tsvector('english', COALESCE(metadata::text, '')), 'B');

-- Backfill existing artifact_versions search_vector
UPDATE mimirdata.artifact_versions SET
    search_vector = to_tsvector('english', COALESCE(content, ''));

-- Comments for documentation
COMMENT ON TABLE mimirdata.embeddings IS 'Vector embeddings for semantic search (one-to-many with artifacts)';
COMMENT ON COLUMN mimirdata.embeddings.model IS 'Embedding model used to generate the vector';
COMMENT ON COLUMN mimirdata.embeddings.embedding IS 'Vector embedding (1536 dimensions for OpenAI text-embedding-3-small)';
COMMENT ON COLUMN mimirdata.embeddings.dimensions IS 'Actual number of dimensions in the embedding';
COMMENT ON COLUMN mimirdata.embeddings.chunk_index IS 'Index for chunked documents (0 = entire document)';
COMMENT ON COLUMN mimirdata.embeddings.chunk_text IS 'Original text chunk used to generate embedding (for debugging)';
COMMENT ON COLUMN mimirdata.artifacts.search_vector IS 'Full-text search vector (title + metadata)';
COMMENT ON COLUMN mimirdata.artifact_versions.search_vector IS 'Full-text search vector (content)';
