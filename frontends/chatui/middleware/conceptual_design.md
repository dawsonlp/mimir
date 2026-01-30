# Middleware Conceptual Design

This document describes the conceptual architecture for the Chat Middleware — the "smart layer" between the thin-client UI and the LLM backend, integrated with Mimir for knowledge persistence.

---

## 1. Overview

The middleware is the intelligence layer of the chat system:

```
┌─────────────┐     ┌─────────────────┐     ┌─────────────┐     ┌─────────┐
│   Chat UI   │────▶│   Middleware    │────▶│   Mimir     │     │   LLM   │
│ (thin client)│◀────│   (smart layer) │◀────│   (memory)  │     │ Backend │
└─────────────┘     └─────────────────┘     └─────────────┘     └─────────┘
                            │                                         │
                            └─────────────────────────────────────────┘
```

**UI responsibilities:** Render messages, collect input, emit events  
**Middleware responsibilities:**
- Map conversation IDs to Mimir artifacts
- Build LLM context from stored artifacts
- Persist messages as artifacts
- Stream LLM responses back to UI
- (Future) Manage complex contexts from multiple artifacts

**Mimir responsibilities:** Store and retrieve knowledge artifacts

---

## 2. Conversation-as-Artifact Model

### Core Mapping

In Mimir, **everything is an artifact**. A conversation is simply an artifact with specific properties:

| Chat Concept | Mimir Representation |
|--------------|---------------------|
| Conversation | Artifact with `artifact_type=conversation` |
| Message | Child artifact (parent_artifact_id → conversation) |
| User message | `artifact_type=message`, metadata `role=user` |
| Assistant message | `artifact_type=message`, metadata `role=assistant` |
| Conversation ID | Mimir artifact UUID |

### Example Structure in Mimir

```
Artifact: conv-abc123
├── artifact_type: conversation
├── title: "Discussion about API design"
├── created_at: 2026-01-07T20:00:00Z
│
├── Child: msg-001 (artifact_type=message)
│   ├── content: "What's the best way to handle authentication?"
│   ├── metadata: {role: "user"}
│   └── created_at: 2026-01-07T20:00:01Z
│
├── Child: msg-002 (artifact_type=message)
│   ├── content: "There are several approaches to authentication..."
│   ├── metadata: {role: "assistant"}
│   └── created_at: 2026-01-07T20:00:05Z
│
└── Child: msg-003 (artifact_type=message)
    ├── content: "Can you explain JWT tokens?"
    ├── metadata: {role: "user"}
    └── created_at: 2026-01-07T20:00:30Z
```

### Benefits

1. **Persistence** — Conversations survive restarts
2. **Search** — Semantic search across all conversation content
3. **Relations** — Link conversations to related artifacts (documents, decisions)
4. **Versioning** — Mimir tracks artifact versions automatically
5. **Provenance** — Who said what, when

---

## 3. Request Flow

### 3.1 New Conversation (conversation_id is null)

```
UI                          Middleware                       Mimir                    LLM
│                               │                              │                       │
│ POST /v1/chat                 │                              │                       │
│ conversation_id: null         │                              │                       │
│ message: "Hello"              │                              │                       │
├──────────────────────────────▶│                              │                       │
│                               │ POST /artifacts              │                       │
│                               │ artifact_type: conversation  │                       │
│                               ├─────────────────────────────▶│                       │
│                               │◀─────────────────────────────┤                       │
│                               │ artifact_id: conv-xyz        │                       │
│                               │                              │                       │
│                               │ POST /artifacts              │                       │
│                               │ parent: conv-xyz             │                       │
│                               │ type: message, role: user    │                       │
│                               ├─────────────────────────────▶│                       │
│                               │                              │                       │
│                               │ Build context (just user msg)│                       │
│                               │                              │                       │
│                               │ Call LLM with context        │                       │
│                               ├──────────────────────────────────────────────────────▶│
│                               │◀──────────────────────────────────────────────────────┤
│                               │ (streaming response)         │                       │
│                               │                              │                       │
│ message.start                 │                              │                       │
│ conversation_id: conv-xyz     │                              │                       │
│◀──────────────────────────────┤                              │                       │
│                               │                              │                       │
│ message.delta (streaming)     │                              │                       │
│◀──────────────────────────────┤                              │                       │
│                               │                              │                       │
│ message.done                  │                              │                       │
│◀──────────────────────────────┤                              │                       │
│                               │                              │                       │
│                               │ POST /artifacts              │                       │
│                               │ parent: conv-xyz             │                       │
│                               │ type: message, role: assistant│                      │
│                               ├─────────────────────────────▶│                       │
│                               │                              │                       │
```

### 3.2 Continue Conversation (conversation_id provided)

```
UI                          Middleware                       Mimir                    LLM
│                               │                              │                       │
│ POST /v1/chat                 │                              │                       │
│ conversation_id: conv-xyz     │                              │                       │
│ message: "Tell me more"       │                              │                       │
├──────────────────────────────▶│                              │                       │
│                               │ GET /artifacts/conv-xyz/     │                       │
│                               │      children                │                       │
│                               ├─────────────────────────────▶│                       │
│                               │◀─────────────────────────────┤                       │
│                               │ [msg-001, msg-002, ...]      │                       │
│                               │                              │                       │
│                               │ POST /artifacts              │                       │
│                               │ parent: conv-xyz             │                       │
│                               │ type: message, role: user    │                       │
│                               ├─────────────────────────────▶│                       │
│                               │                              │                       │
│                               │ Build context from history   │                       │
│                               │                              │                       │
│                               │ Call LLM with full context   │                       │
│                               ├──────────────────────────────────────────────────────▶│
│                               │ (streaming...)               │                       │
│                               │                              │                       │
```

---

## 4. Context Assembly

The middleware's key responsibility is **assembling LLM context** from artifacts.

### Basic Context (Current)

For a simple conversation, context is the ordered list of messages:

```python
def build_context(conversation_id: str) -> list[dict]:
    """Build LLM context from conversation history."""
    # Get all message children, ordered by created_at
    messages = mimir.get_artifact_children(
        conversation_id, 
        artifact_type="message",
        order_by="created_at"
    )
    
    return [
        {"role": msg.metadata["role"], "content": msg.content}
        for msg in messages
    ]
```

### Rich Context (Future)

Context can include more than just conversation history:

```python
def build_rich_context(conversation_id: str, additional_artifacts: list[str]) -> list[dict]:
    """Build context from conversation + additional artifacts."""
    context = []
    
    # Add system context from additional artifacts
    for artifact_id in additional_artifacts:
        artifact = mimir.get_artifact(artifact_id)
        context.append({
            "role": "system",
            "content": f"Reference: {artifact.title}\n\n{artifact.content}"
        })
    
    # Add conversation history
    context.extend(build_context(conversation_id))
    
    return context
```

---

## 5. Future Capabilities

### 5.1 Conversation Branching

Resume from any point in a conversation:

```
UI sends: conversation_id: conv-xyz, branch_from_message: msg-003
Middleware: 
  1. Get messages up to msg-003
  2. Create new conversation artifact linked via "derived_from" relation
  3. Continue from that point
```

### 5.2 Multi-Artifact Context

Assess code using an architecture decision:

```
UI sends: context_artifacts: [artifact-code-123, artifact-adr-456]
Middleware:
  1. Fetch both artifacts
  2. Inject as system context
  3. Start new conversation with enriched context
```

### 5.3 Artifact-as-Conversation-Starter

"Let's discuss this decision record":

```
UI sends: seed_artifact: artifact-decision-789
Middleware:
  1. Fetch the decision artifact
  2. Create conversation with artifact as system context
  3. Generate initial summary/analysis if requested
```

### 5.4 Conversation Summarization

Periodically compress long conversations:

```
Middleware detects conversation > N messages:
  1. Call LLM to summarize
  2. Store summary as artifact
  3. Link summary to conversation via "derived_from"
  4. Use summary instead of full history for context
```

---

## 6. API Compatibility

The middleware implements the same protocol as the echo server:

| Endpoint | Description |
|----------|-------------|
| `POST /v1/chat` | Send message, receive streaming response |
| `GET /health` | Health check |

**UI doesn't need to change** — it speaks the same protocol regardless of whether it's talking to echo-server or middleware.

The `conversation_id` in the protocol maps 1:1 to Mimir artifact IDs. The UI is unaware that conversations are stored as Mimir artifacts.

---

## 7. Configuration

```yaml
# middleware config
mimir:
  base_url: http://localhost:38000
  tenant_id: default

llm:
  provider: openai  # or anthropic, ollama, etc.
  model: gpt-4
  api_key: ${OPENAI_API_KEY}
  
server:
  host: 0.0.0.0
  port: 8000
```

---

## 8. Open Questions

1. **Message granularity** — Store each message as artifact, or batch? (Leaning: each message)

2. **Context window management** — When conversation exceeds LLM context, how to truncate?
   - Sliding window of recent N messages
   - Summarize older messages
   - Semantic selection of relevant messages

3. **Streaming + persistence** — Save assistant message after complete, or incrementally?
   - After complete = simpler, atomic
   - Incrementally = resumable on failure

4. **Artifact type registry** — Do we need `message` type in Mimir, or use existing types?

5. **Tenant isolation** — How to map users to Mimir tenants?

6. **Error handling** — If Mimir save fails, should we still return the response?

---

## 9. Implementation Path

### Phase 1: Minimal Viable Middleware
- [ ] Create/continue conversations as Mimir artifacts
- [ ] Store messages as child artifacts
- [ ] Build simple context from message history
- [ ] Proxy to single LLM provider (OpenAI or Anthropic)
- [ ] Stream responses to UI

### Phase 2: Context Enrichment
- [ ] Accept additional artifact IDs for context
- [ ] Support `seed_artifact` for new conversations
- [ ] Implement context window management

### Phase 3: Advanced Features
- [ ] Conversation branching
- [ ] Automatic summarization
- [ ] Semantic search for relevant context
- [ ] Multi-provider LLM support

---

## 10. Reference

- [Protocol Design](../protocol_design.md) — UI↔Backend protocol specification
- [Mimir API](http://localhost:38000/docs) — Knowledge graph API
- [Echo Server](../echo-server/technical_design.md) — Protocol reference implementation