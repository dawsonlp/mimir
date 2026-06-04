# Mímir Validation Scenarios Tool

## Overview

A command-line tool for validating current Mimir API functionality through real-world usage scenarios. This tool should demonstrate the complete lifecycle of knowledge storage, analysis, retrieval, provenance, and external change visibility.

## Current Status

The implementation currently in `tools/validation-scenarios` is a legacy
V2-era demo scaffold. It should be modernized before being treated as a
contract/conformance suite for Mimir v5.5+.

Modernization requirements:

- Use the published `mimir-client` rather than maintaining a separate thin HTTP
  client.
- Use tenant shortnames as the primary configuration path.
- Exercise unified `POST /search` instead of deprecated `GET /search/fulltext`.
- Validate graph-scoped search and context retrieval against current schemas.
- Validate provenance visibility for committed writes.
- Validate change outbox behavior where the target runtime exposes it.

## Primary Use Case: Multi-Perspective Article Analysis

### Scenario Flow

1. **Ingest Document**: Read a file (text, markdown, etc.) and post it to Mímir as a `document` artifact
2. **Multi-Perspective Analysis**: Use an LLM to analyze the document from multiple perspectives
3. **Store Analyses**: Save each analysis as an `analysis` artifact linked to the source document
4. **Context Retrieval**: Later, retrieve all related analyses to build context for answering questions

### Detailed Requirements

#### 1. Document Ingestion

- Accept a file path as command-line argument
- Extract content and metadata (filename, file type, size)
- Create `document` artifact via Mímir API
- Return artifact UUID for subsequent operations

#### 2. Multi-Perspective Analysis

Analyze the document from predefined perspectives:

| Perspective | Description | Artifact Type |
|-------------|-------------|---------------|
| **Summary** | Concise overview of main points | `summary` |
| **Key Findings** | Important facts, statistics, claims | `finding` |
| **Questions Raised** | Questions the content prompts | `question` |
| **Critical Analysis** | Strengths, weaknesses, assumptions | `analysis` |
| **Actionable Insights** | Practical takeaways | `conclusion` |

Each perspective generates a separate artifact with:
- `parent_artifact_id` pointing to source document (optional)
- `relation` of type `derived_from` linking to source document
- `metadata` containing perspective name and LLM model used

#### 3. Relation Management

For each analysis artifact:
- Create `derived_from` relation: `analysis_id → document_id`
- Store confidence score (default: 1.0 for LLM-generated)
- Include metadata about generation process

#### 4. Context Retrieval

Given a document UUID:
- Query all artifacts related via `derived_from` (or `source_of` inverse)
- Return structured context suitable for RAG:
  - Original document content
  - All analyses organized by perspective
  - Chronological ordering

#### 5. Question Answering Demo

- Accept a question about a stored document
- Retrieve document and all related analyses
- Construct prompt with retrieved context
- Query LLM with augmented prompt
- Return answer with provenance (which artifacts contributed)

## Technical Requirements

### Mímir API Client

Use the published `mimir-client` package as the primary API client. The old
wrapper shape below is retained as historical context and should not be treated
as the target design:

```python
class MimirClient:
    def __init__(self, base_url: str, tenant_id: int)
    
    # Artifacts
    async def create_artifact(self, artifact: ArtifactCreate) -> ArtifactResponse
    async def get_artifact(self, artifact_id: UUID) -> ArtifactResponse
    async def list_artifacts(self, **filters) -> ArtifactListResponse
    
    # Relations
    async def create_relation(self, relation: RelationCreate) -> RelationResponse
    async def get_related_artifacts(self, artifact_id: UUID, direction: str) -> list[RelationResponse]
    
    # Search
    async def semantic_search(self, query: str, **options) -> SearchResponse
```

### LLM Integration

Support for multiple LLM providers:
- **Ollama** (local): Default for testing
- **OpenAI**: For production scenarios
- **Anthropic**: Optional

Configuration via environment variables:
- `LLM_PROVIDER`: ollama | openai | anthropic
- `LLM_MODEL`: Model name (e.g., llama3.2, gpt-4o-mini)
- `OLLAMA_BASE_URL`: http://localhost:11434

### CLI Interface

```bash
# Ingest and analyze a document
mimir-validate ingest article.md --perspectives summary,findings,questions

# Retrieve context for a document
mimir-validate context <document-uuid>

# Ask a question with RAG
mimir-validate ask <document-uuid> "What are the key takeaways?"

# Run full validation scenario
mimir-validate scenario full --file article.md
```

## Configuration

### Environment Variables

```bash
# Mímir API
MIMIR_BASE_URL=http://localhost:38000
MIMIR_TENANT=default

# LLM Provider
LLM_PROVIDER=ollama
LLM_MODEL=llama3.2
OLLAMA_BASE_URL=http://localhost:11434

# Optional: API keys for cloud providers
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
```

### Perspectives Configuration

Perspectives can be customized via YAML:

```yaml
perspectives:
  summary:
    prompt_template: "Summarize the following document in 2-3 paragraphs:\n\n{content}"
    artifact_type: summary
    
  findings:
    prompt_template: "Extract key findings, facts, and statistics from:\n\n{content}"
    artifact_type: finding
    
  questions:
    prompt_template: "What questions does this document raise?\n\n{content}"
    artifact_type: question
```

## Success Criteria

1. **Ingestion**: Document stored with correct metadata and content
2. **Analysis**: Multiple analysis artifacts created from different perspectives
3. **Relations**: All analyses properly linked to source document
4. **Retrieval**: Context includes original document + all related analyses
5. **RAG Demo**: Question answered with context from stored knowledge

## Directory Structure

```
tools/validation-scenarios/
├── docs/
│   └── requirements.md       # This file
├── src/
│   ├── __init__.py
│   ├── client.py            # MimirClient wrapper
│   ├── llm.py               # LLM provider abstraction
│   ├── analyzer.py          # Multi-perspective analyzer
│   ├── scenarios.py         # Validation scenarios
│   └── cli.py               # CLI entry point
├── config/
│   └── perspectives.yaml    # Perspective configurations
├── tests/
│   └── test_scenarios.py
├── pyproject.toml
└── README.md
```

## Dependencies

- `httpx`: Async HTTP client for Mímir API
- `typer`: CLI framework
- `rich`: Terminal output formatting
- `pyyaml`: Configuration loading
- `python-dotenv`: Environment variable management

## Future Enhancements

1. **Embeddings**: Generate and store embeddings for semantic search
2. **Batch Processing**: Process multiple documents
3. **Export**: Export knowledge graph for visualization
4. **Metrics**: Track provenance and usage statistics
