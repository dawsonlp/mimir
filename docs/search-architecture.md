# Mímir V2 Search Architecture

## Overview

Mímir provides three search modes that can be used independently or combined via Reciprocal Rank Fusion.

---

## Search Modes

### Semantic Search

Uses vector similarity via pgvector extension.

**Mechanism:** Cosine distance between query embedding and stored embeddings

**Index:** HNSW (Hierarchical Navigable Small World) for approximate nearest neighbor

**Strengths:**
- Finds conceptually similar content
- Works across synonyms and paraphrases
- Language-agnostic (depends on embedding model)

**Weaknesses:**
- May miss exact keyword matches
- Requires embedding generation (API call)
- Quality depends on embedding model

---

### Full-Text Search

Uses PostgreSQL native text search capabilities.

**Mechanism:** tsvector/tsquery with GIN index

**Strengths:**
- Fast exact phrase matching
- Handles stemming and stop words
- No external API calls needed
- Supports Boolean operators (AND, OR, NOT)

**Weaknesses:**
- Misses semantic similarity
- Language-specific stemming
- No concept of meaning

---

### Hybrid Search (RRF)

Combines semantic and full-text results using Reciprocal Rank Fusion.

**Why RRF?**

Semantic and full-text search return incomparable scores:
- Semantic: similarity scores (0.0 to 1.0)
- Full-text: relevance ranks (arbitrary positive numbers)

RRF solves this by using **rank positions** instead of raw scores.

**RRF Formula:**

For each document, sum contributions from each result list:

`RRF_score = Σ (1 / (k + rank))`

Where:
- k = 60 (constant to prevent over-weighting top results)
- rank = position in each result list (1, 2, 3...)

**Example:**

A document ranking #2 in semantic and #5 in full-text:
- Semantic contribution: 1/(60+2) = 0.0161
- Full-text contribution: 1/(60+5) = 0.0154
- Combined RRF score: 0.0315

This beats a document ranking #1 in only one method (0.0164).

**Key Insight:** Documents appearing in both result sets get boosted—being relevant by multiple criteria indicates higher overall relevance.

---

## Embedding Providers

Pluggable provider architecture with automatic fallback.

### Supported Providers

| Provider | Environment Variable | Best For |
|----------|---------------------|----------|
| Voyage AI | VOYAGE_API_KEY | Production (Anthropic recommended) |
| OpenAI | OPENAI_API_KEY | General purpose |
| Ollama | OLLAMA_BASE_URL | Local/offline |

### Model Selection

| Provider | Models | Dimensions |
|----------|--------|------------|
| Voyage AI | voyage-3, voyage-3-large, voyage-code-3 | 1024, 1024, 1024 |
| OpenAI | text-embedding-3-small, text-embedding-3-large | 1536, 3072 |
| Ollama | nomic-embed-text, all-minilm, mxbai-embed-large | 768, 384, 1024 |

### Provider Fallback

1. Use specified model if provided
2. Otherwise use DEFAULT_EMBEDDING_MODEL from config
3. Otherwise auto-detect first available configured provider

---

## Chunking Strategy

**Key Design Decision:** Chunking is the responsibility of import clients, not the storage layer.

**Rationale:**
- Different content types require different chunking strategies (code, markdown, conversations, legal documents)
- Domain expertise belongs in client applications
- Storage layer stays ontology-agnostic

**Pattern:**
1. Client imports parent document as artifact (type: document)
2. Client creates chunk artifacts (type: chunk)
3. Client creates child_of relations between chunks and parent
4. Client creates embeddings for chunks

**Context Expansion:**
When search returns a chunk, clients can:
1. Retrieve parent via relations (child_of → target)
2. Retrieve sibling chunks for expanded context
3. Include parent metadata in responses

---

## Search Filters (V2)

### Current Filters
- artifact_types: Filter by artifact type(s)
- min_similarity: Minimum similarity threshold for semantic search

### Planned Filters (Phase 7)
- source, source_system: Filter by origin
- created_after, created_before: Date range
- metadata_filters: JSONB containment queries
- parent_artifact_id: Search within specific document's chunks

---

## Performance Considerations

### Indexes

| Type | Purpose |
|------|---------|
| HNSW | Approximate nearest neighbor for vectors |
| GIN | Full-text search on tsvector |
| B-tree | Filtering (tenant_id, artifact_type, created_at) |

### Query Optimization

- All queries include tenant_id filter (uses index)
- Semantic search uses IVFFlat or HNSW for sub-linear search time
- Full-text search leverages GIN index for fast token lookup
- Hybrid search runs both queries in parallel, then fuses
