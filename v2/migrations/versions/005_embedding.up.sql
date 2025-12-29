-- Mímir V2 Migration 005: Embedding
-- Vector representations for semantic search

-- =============================================================================
-- EMBEDDING TABLE - Vector storage for semantic search
-- =============================================================================

CREATE TABLE mimirdata.embedding (
    id SERIAL PRIMARY KEY,
    tenant_id INT NOT NULL REFERENCES mimirdata.tenant(id) ON DELETE CASCADE,
    artifact_id INT NOT NULL REFERENCES mimirdata.artifact(id) ON DELETE CASCADE,
    artifact_version_id INT REFERENCES mimirdata.artifact_version(id) ON DELETE SET NULL,
    model TEXT NOT NULL,                 -- Model name (voyage-3, text-embedding-3-small, nomic-embed-text)
    dimensions INT NOT NULL,             -- Vector dimensions
    embedding vector(2000),              -- pgvector column (HNSW max is 2000 dims)
    chunk_index INT,                     -- Optional chunk position for chunked content
    chunk_text TEXT,                     -- Optional chunk content
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata JSONB DEFAULT '{}'::jsonb
);

-- Primary lookups
CREATE INDEX idx_embedding_tenant ON mimirdata.embedding (tenant_id);
CREATE INDEX idx_embedding_artifact ON mimirdata.embedding (artifact_id);
CREATE INDEX idx_embedding_artifact_version ON mimirdata.embedding (artifact_version_id)
    WHERE artifact_version_id IS NOT NULL;
CREATE INDEX idx_embedding_model ON mimirdata.embedding (tenant_id, model);

-- HNSW index for approximate nearest neighbor search
-- Using cosine distance (most common for text embeddings)
CREATE INDEX idx_embedding_vector ON mimirdata.embedding 
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

COMMENT ON TABLE mimirdata.embedding IS 'Vector representations for semantic search';
COMMENT ON COLUMN mimirdata.embedding.model IS 'Embedding model name (TEXT for flexibility, not enum)';
COMMENT ON COLUMN mimirdata.embedding.dimensions IS 'Actual dimensions of the embedding vector';
COMMENT ON COLUMN mimirdata.embedding.embedding IS 'pgvector column - max 2000 dimensions (HNSW limit)';
COMMENT ON COLUMN mimirdata.embedding.chunk_index IS 'Position of chunk within artifact (0-indexed)';
COMMENT ON COLUMN mimirdata.embedding.chunk_text IS 'Original text that was embedded';
