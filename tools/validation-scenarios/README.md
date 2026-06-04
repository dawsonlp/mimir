# Mímir Validation Scenarios

CLI tool for exercising Mimir through real-world usage scenarios.

## Current Status

This tool predates the current Mimir v5.5 API shape. It is useful as a demo
scaffold, but it is not yet the authoritative v5 contract/conformance suite.

Known modernization gaps:

- It uses a local thin HTTP client instead of the published `mimir-client`.
- It still defaults to integer `MIMIR_TENANT_ID` instead of tenant shortname.
- Search uses the deprecated `GET /search/fulltext` path instead of unified
  `POST /search`.
- It does not yet validate graph-scoped search, provenance, embeddings, or
  change outbox behavior.

The roadmap priority is to convert this into a v5.5 contract validation tool.

## Installation

```bash
cd tools/validation-scenarios
pip install -e .
```

## Configuration

Copy `.env.example` to `.env` and configure:

```bash
cp .env.example .env
```

Required variables:
- `MIMIR_BASE_URL` - Mímir API URL (default: http://localhost:38000)
- `MIMIR_TENANT_ID` - Tenant ID (legacy default: 1)
- `LLM_MODEL` - LLM provider:model (e.g., `ollama:llama3.2` or `anthropic:claude-sonnet-4-5`)

For Anthropic, set `ANTHROPIC_API_KEY`.

## Commands

### Check Status

```bash
mimir-validate status
```

### List Perspectives

```bash
mimir-validate perspectives
```

### Ingest a File

```bash
# Just ingest (no analysis)
mimir-validate ingest article.md

# Ingest and analyze from all perspectives
mimir-validate ingest article.md --perspectives all

# Ingest and analyze from specific perspectives
mimir-validate ingest article.md --perspectives summary,findings
```

### Retrieve Context

```bash
mimir-validate context <artifact-uuid>
mimir-validate context <artifact-uuid> --policy full_graph --depth 3
```

### Search

```bash
mimir-validate search "PostgreSQL"
mimir-validate search "database" --types document,analysis --limit 20
```

## Perspectives

| Name | Artifact Type | Description |
|------|--------------|-------------|
| summary | summary | Concise overview of main points |
| findings | finding | Key facts, statistics, and claims |
| questions | question | Questions the content prompts |
| analysis | analysis | Strengths, weaknesses, assumptions |
| insights | conclusion | Actionable takeaways |

## Example Workflow

```bash
# 1. Check API is running
mimir-validate status

# 2. Ingest a document with all analyses
mimir-validate ingest docs/architecture.md --perspectives all

# 3. Retrieve the document with context
mimir-validate context <document-uuid>

# 4. Search for related content
mimir-validate search "architecture"
