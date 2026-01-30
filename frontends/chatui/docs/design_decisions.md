# Design Decisions Log

This document records architectural decisions made during the development of the Mimir Chat UI project.

---

## DD-001: Thin Client Architecture

**Date:** 2025-01-07  
**Status:** Accepted

### Context
The Chat UI needs to provide a user interface for chat-based interactions while remaining agnostic to backend implementation details (LLMs, RAG, orchestration).

### Decision
Adopt a **thin client** architecture where the UI:
- Only renders messages and collects user input
- Sends requests to a configurable HTTP endpoint
- Has no knowledge of LLMs, context selection, or orchestration
- Delegates all "intelligence" to the backend

### Consequences
- ✅ UI can be swapped independently of backend
- ✅ Backend can be swapped without UI changes
- ✅ Clear separation of concerns
- ⚠️ Requires well-defined protocol contract

---

## DD-002: Streaming Protocol — NDJSON over SSE

**Date:** 2025-01-07  
**Status:** Accepted

### Context
Need to choose a streaming protocol for incremental response delivery. Options considered:
1. Server-Sent Events (SSE)
2. Streamable HTTP (NDJSON)
3. WebSocket

### Decision
Use **Streamable HTTP with NDJSON** as the primary streaming transport, with SSE as an optional fallback.

### Rationale
- Better proxy compatibility than SSE
- Aligns with MCP (Model Context Protocol) streaming patterns
- Single endpoint handles both streaming and non-streaming via content negotiation
- Simpler than WebSocket for request-response patterns

### Consequences
- ✅ Works through all standard HTTP infrastructure
- ✅ MCP-aligned for future interoperability
- ⚠️ No native browser API (requires manual ReadableStream parsing)
- ⚠️ No built-in reconnection (client responsibility)

**Reference:** [protocol_design.md](protocol_design.md)

---

## DD-003: Reject assistant-ui Framework

**Date:** 2025-01-07  
**Status:** Accepted

### Context
Evaluated assistant-ui (React) as a potential UI framework. While feature-rich, its architecture conflicted with our requirements.

### Decision
**Do not use assistant-ui.** Build UI from primitives instead.

### Rationale
assistant-ui's "runtime" abstraction assumes the library:
- Manages conversation state
- Initiates and manages API calls
- Handles streaming parsing

This conflicts with our thin-client requirement where the UI should only render and emit events.

### Consequences
- ✅ Maintains thin-client architecture
- ✅ Full control over protocol implementation
- ⚠️ More initial development effort
- ⚠️ No pre-built AI-specific components

---

## DD-004: Platform Choice — Terminal UI (Textual)

**Date:** 2025-01-07  
**Status:** Accepted

### Context
Need to choose a platform and framework for the Chat UI. Options:
1. Browser SPA (React/TypeScript)
2. Terminal TUI (Textual/Python)
3. Desktop app (PyQt/Electron)

### Decision
Use **Textual** (Python TUI framework) as the primary implementation.

### Rationale
1. **Pure Python** — Aligns with team preference
2. **Truly decoupled** — Widgets are UI-only; HTTP client is separate
3. **Async-native** — Works well with httpx streaming
4. **Cross-platform** — Terminal runs everywhere
5. **Web escape hatch** — Same code deploys to browser via Textual Web
6. **Rich media path** — textual-image for images, Textual Web for full media

### Consequences
- ✅ Single Python codebase
- ✅ Textual Web provides browser option if needed
- ⚠️ Image support depends on terminal capabilities
- ⚠️ Less polished than dedicated web UI

**Reference:** [implementations/textual/technical_design.md](implementations/textual/technical_design.md)

---

## DD-005: Multi-Implementation Structure

**Date:** 2025-01-07  
**Status:** Accepted

### Context
May want multiple UI implementations in the future (web, desktop, etc.).

### Decision
Organize project with:
- Root-level requirements and protocol docs (implementation-agnostic)
- `implementations/` directory with subdirectories per implementation
- Each implementation has its own `technical_design.md`
- Shared `echo-server/` for protocol testing

### Consequences
- ✅ Clear separation between shared spec and implementations
- ✅ Easy to add new implementations
- ✅ Each implementation is self-contained
- ⚠️ Some documentation duplication

---

## DD-006: Echo Server for Protocol Testing

**Date:** 2025-01-07  
**Status:** Accepted

### Context
Need a way to test UI implementations without a real backend.

### Decision
Build a **minimal echo server** that:
- Implements the full chat protocol
- Echoes user messages back
- Supports streaming with simulated delays
- Provides special commands for error testing

### Rationale
- Validates protocol design before building real backend
- Enables UI development without backend dependency
- Tests edge cases (errors, slow responses, long content)

### Consequences
- ✅ Enables parallel development of UI and backend
- ✅ Provides regression testing for protocol compliance
- ⚠️ Doesn't test real AI response patterns

**Reference:** [echo-server/technical_design.md](echo-server/technical_design.md)

---

## DD-007: Transcript Logging with Extension-Based Format Detection

**Date:** 2026-01-07  
**Status:** Accepted

### Context
Terminal UIs have limited text selection capabilities. Users need a way to easily copy and share conversation content without relying on terminal copy mode or per-message copy buttons.

### Decision
Add optional **transcript file logging** with format detection based on file extension:

**Usage:**
```bash
poetry run python -m src.chat_app transcript.md    # Markdown
poetry run python -m src.chat_app transcript.json  # NDJSON
```

**Behavior:**
- File argument is optional (no file = no logging)
- File doesn't exist → create and start logging
- File exists → append to existing file
- Messages written immediately as they complete

**Format detection:**
| Extension | Format |
|-----------|--------|
| `.md`, `.markdown` | Markdown |
| `.json`, `.jsonl`, `.ndjson` | NDJSON |
| Other | Markdown (default) |

**Markdown format:**
```markdown
### You
Hello, World!

### Assistant  
Echo: Hello, World!
```

**NDJSON format:**
```json
{"role":"user","content":"Hello, World!","timestamp":"2026-01-07T19:58:00Z"}
{"role":"assistant","content":"Echo: Hello, World!","timestamp":"2026-01-07T19:58:01Z"}
```

### Rationale
1. **Solves copy problem** — Full conversation available outside the TUI
2. **Extension convention** — Natural and familiar pattern for users
3. **Append mode** — Allows resuming sessions and multi-session logs
4. **Two formats** — Markdown for human reading, NDJSON for programmatic access
5. **Optional** — Doesn't change behavior when not specified

### Consequences
- ✅ Easy export without terminal selection limitations
- ✅ Machine-readable format available for tooling
- ✅ Supports session continuity/history
- ⚠️ Streaming messages logged only when complete (not incrementally)
- ⚠️ No automatic file rotation/management

---

## DD-008: Conversation-as-Artifact Architecture

**Date:** 2026-01-07  
**Status:** Accepted

### Context
The chat system needs to persist conversations and integrate with Mimir, the knowledge graph and semantic memory system. Need to decide how chat concepts map to Mimir's artifact model.

### Decision
**Conversations are Mimir artifacts.** The middleware maps chat concepts to Mimir as follows:

| Chat Concept | Mimir Representation |
|--------------|---------------------|
| Conversation | Artifact with `artifact_type=conversation` |
| Message | Child artifact with `artifact_type=message` |
| conversation_id | Mimir artifact UUID |

The middleware is responsible for:
1. Creating conversation artifacts on new chat
2. Storing each message as a child artifact
3. Building LLM context from artifact history
4. Streaming responses back to UI

### Rationale
1. **Everything is an artifact** — Aligns with Mimir's unified model
2. **Enables relations** — Conversations can link to documents, decisions, code
3. **Semantic search** — Messages are searchable across all conversations
4. **Provenance** — Full audit trail of who said what, when
5. **Future-proof** — Supports branching, summarization, multi-artifact context

### Consequences
- ✅ Conversations persist and survive restarts
- ✅ Rich querying and relation capabilities
- ✅ UI protocol unchanged (conversation_id = artifact_id)
- ⚠️ Middleware complexity (must manage artifacts)
- ⚠️ Depends on Mimir availability

**Reference:** [middleware/conceptual_design.md](middleware/conceptual_design.md)

---

## Template for Future Decisions

```markdown
## DD-XXX: [Title]

**Date:** YYYY-MM-DD  
**Status:** Proposed | Accepted | Deprecated | Superseded

### Context
[What is the issue being addressed?]

### Decision
[What was decided?]

### Rationale
[Why was this decision made?]

### Consequences
[What are the results of this decision?]