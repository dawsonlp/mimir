# Requirements

## Version 1 — Durable Memory & Intent Capture (Foundation)

### Primary Goal

Create a reliable system that ingests conversations and documents, extracts structure and intent, and supports search, recall, and basic meta-workflow—without over-automation.

### Core Capabilities

#### Ingestion

- Import ChatGPT exports (conversations.json) as canonical artifacts.
- Ingest user-authored documents and notes.
- Preserve raw content unchanged (append-only canonical store).

#### Content Model

- Store conversations and documents as Artifacts.
- Represent structure using relations (contains, precedes).
- Support Spans for precise provenance.

#### Intent & Decisions

- Create Intent objects (human- or LLM-proposed).
- Create Intent Groups as a semi-managed vocabulary.
- Record Decisions with:
  - statement
  - rationale
  - source span
  - status (active / superseded / tentative)

#### Summaries & TOCs

- Generate and store:
  - thread-level summaries
  - conversation Tables of Contents (span-based)
- Treat all LLM outputs as proposals requiring acceptance.

#### Search & Retrieval

- Lexical search via full-text indexing.
- Semantic search via embeddings.
- Support multiple embedding models with explicit embedding-space provenance.

#### Governance

- Track provenance for all derived artifacts:
  - model used
  - prompt/version
  - evidence spans
- Human authority is final.

### Explicit Non-Goals (V1)

- Automated intent drift timelines
- Aside splitting
- Ontology schemas or fixed hierarchies
- Argument graphs
- Fully automated tagging justification

---

## Version 2 — Meta-Workflow & Reflective Analysis

### Primary Goal

Enable reflection on conversations themselves: effectiveness, redundancy, intent drift, and quality of inquiry.

### Added Capabilities

#### Intent Dynamics

- Track intent assignment over time (intent timelines).
- Detect and surface intent drift.
- Support multiple active intents per conversation window.

#### Redundancy & Recall

- Detect when a new prompt overlaps with:
  - prior intents
  - prior decisions
- Offer decision recall summaries instead of re-exploration.

#### Asides & Branching

- Identify candidate asides (intent divergence).
- Allow extraction into:
  - separate threads
  - parked intents
- Preserve bidirectional links.

#### Conversation Meta-Analysis

- Generate Conversation Reviews answering:
  - How well did this conversation serve its intent?
  - Where did it stall or diverge?
  - What was the most productive segment?
  - What would have been a better initial prompt?
- Produce canonical "compressed" versions of long conversations.

#### Subject & Vocabulary Refinement

- Introduce optional justified tagging (tags backed by analysis).
- Merge, deprecate, and evolve Intent Groups deliberately.

---

## Version 3 — Multi-Ontology & Synthesis Engine

### Primary Goal

Support multiple concurrent worldviews and analytical lenses over the same corpus, enabling synthesis rather than mere retrieval.

### Advanced Capabilities

#### Ontology Views

- Define ontology schemas (e.g., argument graph, narrative arc, system architecture).
- Materialize multiple views over the same artifacts.
- Compare views without privileging a single "true" structure.

#### Cross-Intent & Cross-Group Synthesis

- Generate summaries across:
  - intent groups
  - projects
  - time ranges
- Produce comparative matrices (e.g., technology evaluations).
- Detect conceptual conflicts between decisions.

#### Advanced Retrieval

- Hybrid lexical + semantic + structural retrieval.
- Span-aware reranking and evidence aggregation.
- Concept- and intent-aware search scopes.

#### Longitudinal Insight

- Track how beliefs, decisions, and models evolve over time.
- Surface "what changed and why."
- Enable reflective self-audit of reasoning patterns.

---

## One-Line Roadmap Summary

| Version | Focus |
|---------|-------|
| **V1** | Remember accurately. |
| **V2** | Reflect intelligently. |
| **V3** | Synthesize wisely. |

---

## Storage System Non-Goals (V1–V3)

These are crisp statements of what the storage API deliberately does not do, and why.

### 1. No Orchestration or Workflow Execution

**Non-goal:** The storage system does not run LangGraph graphs, schedule jobs, coordinate agents, or manage tool calls (including MCP).

**Why:** Orchestration changes rapidly; storage must remain stable. Keep the store "dumb" and composable.

### 2. No Ingestion Logic Beyond Basic Acceptance and Validation

**Non-goal:** The storage system does not chunk documents, extract TOCs, infer intents, summarize, tag, or perform entity extraction.

**Why:** Those are interpretation/compute steps. The store should accept outputs and record provenance, not generate them.

> Note: It may accept pre-chunked artifacts/spans and store them.

### 3. No LLM Calls (and No Model-Specific Behavior)

**Non-goal:** The storage system does not call LLMs or embedding endpoints, and does not embed model-specific prompt logic.

**Why:** Keeps billing, secrets, model choice, and failure modes outside the storage boundary. Model evolution should not force storage redeploys.

### 4. No "Truth Adjudication" or Semantic Authority

**Non-goal:** The storage system does not decide which analysis/summary/intent is correct, and does not collapse competing interpretations into one truth.

**Why:** The store supports multiple views and versions. Authority belongs to higher layers (human governance + workflow).

### 5. No UI or Presentation Logic

**Non-goal:** The storage system does not format outputs for a specific UI (chat panes, sidebars, markdown rendering conventions, etc.).

**Why:** Prevents coupling to LibreChat/NOI/custom UI. The store returns data; clients decide presentation.

### 6. No Hard-Coded Ontology or Fixed Hierarchy

**Non-goal:** The storage system does not enforce "book → chapter → paragraph" or any single canonical content model.

**Why:** You explicitly want alternative ontologies/views. The store supports relations and views, but does not impose one.

### 7. No Irreversible Transforms or Destructive Edits of Canonical Content

**Non-goal:** The storage system never mutates canonical ingested content in-place or overwrites history.

**Why:** Auditability and reproducibility depend on canonical truth staying intact. Use versioning/upserts with history.

### 8. No Global Semantic Index Semantics Beyond Storage and Retrieval Primitives

**Non-goal:** The storage system does not implement "meaning-based policies" like auto-merging concepts, auto-deprecating intent groups, or auto-generating "best" embeddings.

**Why:** Those are governance and analysis decisions. The store can support them, but should not perform them implicitly.

### 9. No Security Policy Beyond Access Control Boundaries

**Non-goal:** The storage system does not encode domain-specific compliance policy, redaction logic, or privacy heuristics beyond basic authentication/authorization and data partitioning.

**Why:** Policy differs by deployment and evolves; put it in a policy layer if needed. (The store must support scopes/tenants/ownership, but not interpret content for policy.)

### 10. No "Automatic Lifecycle Management" of Knowledge

**Non-goal:** The storage system does not automatically delete, archive, summarize-away, or compress content as it grows.

**Why:** This is value-laden and risks silent loss. Storage may expose retention tooling/hooks, but decisions belong elsewhere.

---

## Boundary Clarification: What the Storage System May Do

To avoid ambiguity, these are "allowed" capabilities that still fit the storage role:

- Validation of shapes (IDs, required fields, allowed relation types if you define a registry)
- Idempotent upserts and version history
- Index maintenance (FTS, vector indexes, graph adjacency)
- Query execution (search, filtering, traversal)
- Provenance recording (model IDs, pipeline versions, source spans)
- Lightweight registry of embedding spaces and vocabularies (authority objects), as data—not logic

That's still "boring substrate."

---

## Compact Non-Goals Summary

For quick reference:

1. No LLM calls.
2. No ingestion/chunking/summarization/intent inference.
3. No workflow orchestration (LangGraph/MCP).
4. No UI/presentation logic.
5. No fixed ontology; only relations + versioned views.
6. No truth adjudication; store competing interpretations.
7. No destructive edits; canonical content is append-only/versioned.
8. No automatic retention/archiving decisions.
