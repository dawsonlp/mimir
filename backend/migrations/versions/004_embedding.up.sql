-- Mímir V2 Migration 004: Embedding (Multi-Model Architecture)
-- Vector representations for semantic search with dynamic model support
-- See docs/embedding-architecture-design.md for full design rationale

-- =============================================================================
-- VECTOR SCHEMA - Separate schema for dynamically-created vector tables
-- =============================================================================

CREATE SCHEMA IF NOT EXISTS mimir_vectors;

COMMENT ON SCHEMA mimir_vectors IS 'Schema for dynamically-created vector tables (one per embedding model)';

-- =============================================================================
-- EMBEDDING_TYPE VOCABULARY TABLE
-- =============================================================================

CREATE TABLE mimirdata.embedding_type (
    code TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    provider TEXT NOT NULL,              -- 'ollama', 'openai', 'voyage', etc.
    dimensions INT NOT NULL,             -- Fixed dimensions for this model
    distance_metric TEXT NOT NULL DEFAULT 'cosine',  -- 'cosine', 'l2', 'inner_product'
    max_tokens INT,                      -- Max input tokens for the model
    description TEXT,
    vector_table_name TEXT NOT NULL,     -- Name of vector table in mimir_vectors schema
    is_active BOOLEAN NOT NULL DEFAULT true,
    sort_order INT DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    
    -- Validation: code must match pattern (lowercase, numbers, hyphens, 3-50 chars)
    CONSTRAINT embedding_type_code_pattern CHECK (code ~ '^[a-z][a-z0-9-]{2,49}$'),
    -- Validation: distance_metric must be valid
    CONSTRAINT embedding_type_distance_metric CHECK (distance_metric IN ('cosine', 'l2', 'inner_product')),
    -- Validation: dimensions must be positive and within pgvector limits
    CONSTRAINT embedding_type_dimensions CHECK (dimensions > 0 AND dimensions <= 16000)
);

CREATE INDEX idx_embedding_type_provider ON mimirdata.embedding_type (provider);
CREATE INDEX idx_embedding_type_active ON mimirdata.embedding_type (is_active) WHERE is_active = true;

COMMENT ON TABLE mimirdata.embedding_type IS 'Vocabulary table for embedding models - each creates a vector table in mimir_vectors schema';
COMMENT ON COLUMN mimirdata.embedding_type.code IS 'Unique code for embedding type (lowercase alphanumeric + hyphens)';
COMMENT ON COLUMN mimirdata.embedding_type.dimensions IS 'Fixed vector dimensions for this model';
COMMENT ON COLUMN mimirdata.embedding_type.vector_table_name IS 'Name of corresponding table in mimir_vectors schema';

-- =============================================================================
-- EMBEDDING TABLE - Metadata only (no vector column)
-- =============================================================================

CREATE TABLE mimirdata.embedding (
    id UUID PRIMARY KEY DEFAULT uuidv7(),
    tenant_id INT NOT NULL REFERENCES mimirdata.tenant(id) ON DELETE CASCADE,
    artifact_id UUID NOT NULL REFERENCES mimirdata.artifact(id) ON DELETE CASCADE,
    embedding_type TEXT NOT NULL REFERENCES mimirdata.embedding_type(code),
    
    -- Timestamp (no updated_at - append only)
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    
    -- Extensible properties
    metadata JSONB DEFAULT '{}'::jsonb
);

-- Primary lookups
CREATE INDEX idx_embedding_tenant ON mimirdata.embedding (tenant_id);
CREATE INDEX idx_embedding_artifact ON mimirdata.embedding (artifact_id);
CREATE INDEX idx_embedding_type ON mimirdata.embedding (tenant_id, embedding_type);

-- Timestamp for queries
CREATE INDEX idx_embedding_created ON mimirdata.embedding (tenant_id, created_at DESC);

-- Unique constraint: one embedding per artifact per type (within tenant)
CREATE UNIQUE INDEX idx_embedding_artifact_type ON mimirdata.embedding (tenant_id, artifact_id, embedding_type);

COMMENT ON TABLE mimirdata.embedding IS 'Embedding metadata - vectors stored in mimir_vectors.vec_{type} tables';
COMMENT ON COLUMN mimirdata.embedding.id IS 'UUID primary key - server-generated';
COMMENT ON COLUMN mimirdata.embedding.embedding_type IS 'FK to embedding_type - determines which vector table holds the data';

-- =============================================================================
-- NOTE: Vector tables are created dynamically by the API
-- =============================================================================
-- When POST /embedding-types is called with code='nomic-embed-text' and dimensions=768,
-- the API creates:
--
-- CREATE TABLE mimir_vectors.vec_nomic_embed_text (
--     embedding_id UUID PRIMARY KEY REFERENCES mimirdata.embedding(id) ON DELETE CASCADE,
--     embedding vector(768) NOT NULL
-- );
--
-- CREATE INDEX idx_vec_nomic_embed_text_hnsw 
--     ON mimir_vectors.vec_nomic_embed_text 
--     USING hnsw (embedding vector_cosine_ops)
--     WITH (m = 16, ef_construction = 64);
--
-- This approach allows:
-- 1. Each model to have its own HNSW index with correct dimensions
-- 2. Dynamic addition of new embedding models via API
-- 3. Schema isolation (DDL only in mimir_vectors)
