# Embedding Architecture Redesign

## Problem Statement

pgvector's HNSW index requires fixed dimensions. Different embedding models produce different dimensions:

| Model | Provider | Dimensions |
|-------|----------|------------|
| nomic-embed-text | Ollama | 768 |
| all-minilm | Ollama | 384 |
| text-embedding-3-small | OpenAI | 1536 |
| text-embedding-3-large | OpenAI | 3072 |
| voyage-3 | Voyage AI | 1024 |
| voyage-3-large | Voyage AI | 2048 |

The current design uses `vector(2000)` which:
1. Requires exactly 2000 dimensions (not a max)
2. Can't accommodate 768-dim or 3072-dim models without padding/truncation
3. Breaks the HNSW index for non-2000-dim vectors

## Design Goals

1. **Support multiple embedding models** with different dimensions
2. **Maintain HNSW indexes** for efficient similarity search (each with fixed dimension)
3. **Dynamic registration** of new embedding types via API
4. **Single query interface** for embeddings (hide the complexity)
5. **Follow existing vocabulary table pattern** (artifact_type, relation_type, tenant_type)

## Proposed Architecture

### Schema Isolation for Security

Two schemas with different privilege models:

| Schema | Purpose | API Privileges |
|--------|---------|----------------|
| `mimirdata` | Structured data (artifacts, relations, metadata) | SELECT, INSERT, UPDATE, DELETE |
| `mimir_vectors` | Dynamically-created vector tables | ALL (including DDL) |

This isolates DDL operations to a dedicated schema, minimizing risk.

### Code Validation Pattern

```python
# Embedding type codes must match this pattern:
# - Lowercase letters, numbers, hyphens only
# - Must start with a letter
# - 3-50 characters
import re
EMBEDDING_TYPE_CODE_PATTERN = re.compile(r'^[a-z][a-z0-9-]{2,49}$')
```

### 1. Embedding Type Vocabulary Table

```sql
CREATE TABLE mimirdata.embedding_type (
    code TEXT PRIMARY KEY,               -- e.g., 'nomic-embed-text', 'voyage-3'
    display_name TEXT NOT NULL,
    provider TEXT NOT NULL,              -- 'ollama', 'openai', 'voyage', etc.
    dimensions INT NOT NULL,             -- Fixed dimensions for this model
    distance_metric TEXT DEFAULT 'cosine', -- 'cosine', 'l2', 'inner_product'
    max_tokens INT,                      -- Max input tokens for the model
    description TEXT,
    vector_table_name TEXT NOT NULL,     -- Name of vector table in mimir_vectors schema
    is_active BOOLEAN NOT NULL DEFAULT true,
    sort_order INT DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    
    -- Validation: code must match pattern
    CONSTRAINT embedding_type_code_pattern CHECK (code ~ '^[a-z][a-z0-9-]{2,49}$')
);
```

### 2. Master Embedding Table (Metadata Only - No Vector)

```sql
CREATE TABLE mimirdata.embedding (
    id UUID PRIMARY KEY DEFAULT uuidv7(),
    tenant_id INT NOT NULL REFERENCES mimirdata.tenant(id) ON DELETE CASCADE,
    artifact_id UUID NOT NULL REFERENCES mimirdata.artifact(id) ON DELETE CASCADE,
    embedding_type TEXT NOT NULL REFERENCES mimirdata.embedding_type(code),
    
    -- Metadata
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata JSONB DEFAULT '{}'::jsonb
    
    -- NOTE: No 'embedding' vector column - stored in child table
);
```

### 3. Child Vector Tables (Per Embedding Type)

Child vector tables live in the **`mimir_vectors`** schema (separate from `mimirdata`):

```sql
-- Example: Created when 'nomic-embed-text' is registered (768 dims)
CREATE TABLE mimir_vectors.vec_nomic_embed_text (
    embedding_id UUID PRIMARY KEY REFERENCES mimirdata.embedding(id) ON DELETE CASCADE,
    embedding vector(768) NOT NULL
);

CREATE INDEX idx_vec_nomic_embed_text_hnsw 
    ON mimir_vectors.vec_nomic_embed_text 
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
```

### 4. Table Naming Convention

Child tables in `mimir_vectors` follow the pattern: `vec_{sanitized_code}`

Where `sanitized_code` replaces hyphens with underscores:
- `nomic-embed-text` → `mimir_vectors.vec_nomic_embed_text`
- `text-embedding-3-small` → `mimir_vectors.vec_text_embedding_3_small`
- `voyage-3` → `mimir_vectors.vec_voyage_3`

## API Design

### Embedding Types API

```
POST   /embedding-types              -- Create type + child vector table
GET    /embedding-types              -- List all types
GET    /embedding-types/{code}       -- Get type details
DELETE /embedding-types/{code}       -- Soft delete (set is_active=false)
```

**POST /embedding-types** (Creates type AND child table):
```json
{
    "code": "nomic-embed-text",
    "display_name": "Nomic Embed Text",
    "provider": "ollama",
    "dimensions": 768,
    "distance_metric": "cosine",
    "max_tokens": 8192,
    "description": "Good balance of quality and speed"
}
```

### Embeddings API (Enhanced)

```
POST   /embeddings                   -- Create embedding (inserts to master + child)
GET    /embeddings                   -- List embeddings (from master table)
GET    /embeddings/{id}              -- Get embedding (optionally with vector)
GET    /embeddings/artifact/{id}     -- Get artifact's embeddings
POST   /embeddings/similar           -- Find similar (queries appropriate child table)
```

**POST /embeddings** request:
```json
{
    "artifact_id": "uuid-here",
    "embedding_type": "nomic-embed-text",
    "embedding": [0.1, 0.2, ...],  // 768 values
    "metadata": {}
}
```

The service:
1. Looks up `embedding_type` to get dimensions and table name
2. Validates vector length matches expected dimensions
3. Inserts to master `embedding` table
4. Inserts to child `embedding_vec_nomic_embed_text` table

**POST /embeddings/similar** request:
```json
{
    "query_vector": [0.1, 0.2, ...],
    "embedding_type": "nomic-embed-text",  // Required to know which table
    "limit": 20,
    "similarity_threshold": 0.7
}
```

The service:
1. Looks up the child table for the embedding type
2. Queries that specific table's HNSW index

## Query Patterns

### Find similar artifacts

```sql
SELECT e.id, e.artifact_id, e.embedding_type,
       1 - (v.embedding <=> $query_vector) as similarity
FROM mimirdata.embedding e
JOIN mimir_vectors.vec_nomic_embed_text v ON v.embedding_id = e.id
WHERE e.tenant_id = $tenant_id
  AND e.embedding_type = 'nomic-embed-text'
ORDER BY v.embedding <=> $query_vector
LIMIT 20;
```

### Get embedding with vector

```sql
SELECT e.*, v.embedding
FROM mimirdata.embedding e
JOIN mimir_vectors.vec_nomic_embed_text v ON v.embedding_id = e.id
WHERE e.id = $embedding_id AND e.tenant_id = $tenant_id;
```

## Dynamic Table Creation

When `POST /embedding-types` is called, the service must execute DDL in the **`mimir_vectors`** schema:

```python
async def create_embedding_type(data: EmbeddingTypeCreate) -> EmbeddingType:
    # 1. Validate code pattern
    if not EMBEDDING_TYPE_CODE_PATTERN.match(data.code):
        raise ValueError("Invalid code format")
    
    # 2. Generate table name (hyphens → underscores)
    table_name = f"vec_{data.code.replace('-', '_')}"
    
    # 3. Insert to embedding_type vocabulary table
    await insert_embedding_type(data, vector_table_name=table_name)
    
    # 4. Create child vector table in mimir_vectors schema
    ddl = f"""
    CREATE TABLE mimir_vectors.{table_name} (
        embedding_id UUID PRIMARY KEY REFERENCES mimirdata.embedding(id) ON DELETE CASCADE,
        embedding vector({data.dimensions}) NOT NULL
    );
    """
    
    # 5. Create HNSW index
    ops = get_distance_ops(data.distance_metric)
    index_ddl = f"""
    CREATE INDEX idx_{table_name}_hnsw 
        ON mimir_vectors.{table_name} 
        USING hnsw (embedding {ops})
        WITH (m = 16, ef_construction = 64);
    """
    
    # Execute DDL (API has DDL rights on mimir_vectors only)
    await conn.execute(ddl)
    await conn.execute(index_ddl)
    
    return result
```

### Distance Metric Operators

```python
def get_distance_ops(metric: str) -> str:
    return {
        'cosine': 'vector_cosine_ops',
        'l2': 'vector_l2_ops',
        'inner_product': 'vector_ip_ops',
    }.get(metric, 'vector_cosine_ops')
```

## Security Considerations

1. **Code validation**: The `code` value is validated against `^[a-z][a-z0-9-]{2,49}$` pattern (no SQL injection risk)
2. **Schema isolation**: DDL rights restricted to `mimir_vectors` schema only
3. **Table proliferation**: Monitor for excessive table creation; consider limits
4. **Cross-schema references**: Vector tables reference `mimirdata.embedding(id)` with ON DELETE CASCADE

## Seed Data

**No pre-seeded embedding types.** All types are created via API calls. This keeps the migration simple and allows dynamic registration.

## Migration Strategy

### Migration 004 (Updated)

```sql
-- Part 1: Create mimir_vectors schema (for dynamically-created tables)
-- Part 2: Create embedding_type vocabulary table (empty, no seeds)
-- Part 3: Create master embedding table (no vector column)
-- Part 4: Grant DDL privileges on mimir_vectors to API user
```

### Existing Data

Since Mímir is in development with no production embeddings, we can:
1. Drop the existing `embedding` table
2. Create new schema
3. No data migration needed

## Benefits

1. **Proper HNSW indexes** - Each embedding type gets its own optimized index
2. **No padding/truncation** - Store exactly the dimensions the model produces
3. **Extensibility** - Add new models via API without schema migration
4. **Clear separation** - Metadata in master, vectors in optimized child tables
5. **Consistent pattern** - Follows vocabulary table pattern (artifact_type, etc.)

## Tradeoffs

1. **Multiple tables** - More tables to manage (one per embedding type)
2. **Join required** - Queries need to join master + child table
3. **DDL at runtime** - API creates tables dynamically (needs proper privileges)
4. **Cross-type search** - Cannot easily search across different embedding types in one query (but this is mathematically meaningless anyway)

## Future Considerations

1. **Table partitioning** - Could partition child tables by tenant_id for very large deployments
2. **Auto-embedding** - API could optionally generate embeddings if only text is provided
3. **Batch operations** - Efficient bulk embedding creation

---

*Drafted: January 2026*
