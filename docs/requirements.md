# Mímir Requirements

## Version Roadmap

| Version | Focus | Description |
|---------|-------|-------------|
| **V1** | Remember accurately | Durable memory & intent capture |
| **V2** | Reflect intelligently | Meta-workflow & reflective analysis |
| **V3** | Synthesize wisely | Multi-ontology & synthesis engine |

---

## V1: Durable Memory & Intent Capture (Foundation)

### Primary Goal
Create a reliable system that ingests conversations and documents, extracts structure and intent, and supports search, recall, and basic meta-workflow—without over-automation.

### Core Capabilities

| Capability | Description |
|------------|-------------|
| **Ingestion** | Import ChatGPT exports, user documents, notes. Preserve raw content unchanged (append-only). |
| **Content Model** | Artifacts for storage. Relations for structure. Spans for precise provenance. |
| **Intent & Decisions** | Intent objects, Intent Groups, Decisions with statement/rationale/status |
| **Summaries & TOCs** | Thread-level summaries, conversation TOCs. LLM outputs as proposals. |
| **Search & Retrieval** | Lexical (full-text), semantic (embeddings), multiple embedding models |
| **Governance** | Track provenance (model, prompt, evidence spans). Human authority is final. |

### V1 Non-Goals
- Automated intent drift timelines
- Aside splitting
- Ontology schemas or fixed hierarchies
- Argument graphs
- Fully automated tagging justification

---

## V2: Meta-Workflow & Reflective Analysis

### Primary Goal
Enable reflection on conversations: effectiveness, redundancy, intent drift, quality of inquiry.

### Added Capabilities

| Capability | Description |
|------------|-------------|
| **Intent Dynamics** | Track intent assignment over time, detect drift, multiple active intents |
| **Redundancy & Recall** | Detect overlap with prior intents/decisions, offer recall summaries |
| **Asides & Branching** | Identify asides, extract to separate threads, preserve links |
| **Conversation Meta-Analysis** | Generate reviews: effectiveness, stalls, productive segments, better prompts |
| **Vocabulary Refinement** | Justified tagging, merge/deprecate Intent Groups deliberately |

---

## V3: Multi-Ontology & Synthesis Engine

### Primary Goal
Support multiple concurrent worldviews and analytical lenses over the same corpus, enabling synthesis rather than mere retrieval.

### Advanced Capabilities

| Capability | Description |
|------------|-------------|
| **Ontology Views** | Define schemas (argument graph, narrative arc). Materialize multiple views. |
| **Cross-Intent Synthesis** | Summaries across groups/projects/time. Comparative matrices. Conflict detection. |
| **Advanced Retrieval** | Hybrid lexical + semantic + structural. Span-aware reranking. |
| **Longitudinal Insight** | Track belief/decision/model evolution. Surface "what changed and why." |

---

## Storage System Non-Goals (All Versions)

These define what the storage API **deliberately does not do**.

### 1. No Orchestration
Does not run workflows, schedule jobs, coordinate agents, or manage tool calls.

### 2. No Ingestion Logic
Does not chunk documents, extract TOCs, infer intents, summarize, or perform entity extraction.
> May accept pre-chunked artifacts/spans and store them.

### 3. No LLM Calls
Does not call LLMs or embedding endpoints. Does not embed model-specific prompt logic.

### 4. No Truth Adjudication
Does not decide which analysis is correct. Does not collapse competing interpretations.

### 5. No UI/Presentation
Does not format outputs for specific UIs. Returns data; clients decide presentation.

### 6. No Fixed Ontology
Does not enforce any single canonical content model. Supports relations and views.

### 7. No Destructive Edits
Never mutates canonical content in-place or overwrites history. Append-only.

### 8. No Auto-Semantic Policies
Does not auto-merge concepts, auto-deprecate groups, or auto-generate "best" embeddings.

### 9. No Content-Based Security
Does not encode domain-specific compliance, redaction, or privacy heuristics beyond access control.

### 10. No Automatic Lifecycle
Does not auto-delete, archive, summarize-away, or compress content.

---

## What Storage May Do

Allowed capabilities that fit the storage role:

- Shape validation (IDs, required fields, allowed relation types)
- Idempotent upserts and version history
- Index maintenance (FTS, vector, graph adjacency)
- Query execution (search, filtering, traversal)
- Provenance recording (model IDs, pipeline versions, source spans)
- Registry of embedding spaces and vocabularies as data (not logic)

---

## Compact Non-Goals Reference

1. No LLM calls
2. No ingestion/chunking/summarization/inference
3. No workflow orchestration
4. No UI/presentation logic
5. No fixed ontology
6. No truth adjudication
7. No destructive edits
8. No automatic retention decisions
