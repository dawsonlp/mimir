-- Mímir V2 Migration 004: Embedding
-- Vector representations for semantic search (append-only)

-- =============================================================================
-- EMBEDDING TABLE - Vector storage for semantic search (Append-Only)
-- =============================================================================

CREATE TABLE mimirdata.embedding (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id INT NOT NULL REFERENCES mimirdata.tenant(id) ON DELETE CASCADE,
    artifact_id UUID NOT NULL REFERENCES mimirdata.artifact(id) ON DELETE CASCADE,
    
    -- Model info (TEXT for flexibility - new models can be added without schema change)
    model TEXT NOT NULL,                 -- Model name (voyage-3, text-embedding-3-small, nomic-embed-text)
    dimensions INT NOT NULL,             -- Actual vector dimensions
    
    -- Vector storage
    embedding vector(2000),              -- pgvector column (HNSW max is 2000 dims)
    
    -- Timestamp (no updated_at - append only)
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    
    -- Extensible properties
    metadata JSONB DEFAULT '{}'::jsonb
);

-- Primary lookups
CREATE INDEX idx_embedding_tenant ON mimirdata.embedding (tenant_id);
CREATE INDEX idx_embedding_artifact ON mimirdata.embedding (artifact_id);
CREATE INDEX idx_embedding_model ON mimirdata.embedding (tenant_id, model);

-- Timestamp for queries
CREATE INDEX idx_embedding_created ON mimirdata.embedding (tenant_id, created_at DESC);

-- HNSW index for approximate nearest neighbor search
-- Using cosine distance (most common for text embeddings)
CREATE INDEX idx_embedding_vector ON mimirdata.embedding 
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

COMMENT ON TABLE mimirdata.embedding IS 'Vector representations for semantic search (append-only)';
COMMENT ON COLUMN mimirdata.embedding.id IS 'UUID primary key - server-generated';
COMMENT ON COLUMN mimirdata.embedding.model IS 'Embedding model name (TEXT for flexibility)';
COMMENT ON COLUMN mimirdata.embedding.dimensions IS 'Actual dimensions of the embedding vector';
COMMENT ON COLUMN mimirdata.embedding.embedding IS 'pgvector column - max 2000 dimensions (HNSW limit)';
