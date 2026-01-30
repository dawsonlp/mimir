# Thin Chat UI (Client Only)

## Intent

Provide a clean, easily styled, easily extended chat user interface that acts as a **thin client**.

The Chat UI's only job is to:

1. Collect user input
2. Send it to a configurable backend endpoint using a stable protocol
3. Render responses (including streaming)
4. Manage local conversation state for UX

> **Important:** The Chat UI must not contain any middleware logic (context selection, RAG, tool calling, LLM/provider integration, persistence into Mimir).

---

## 1. Scope

### In Scope (Chat UI Responsibilities)

| Area | Details |
|------|---------|
| **Single-page chat experience** | Message list, input composer, send/stop/retry, streaming display |
| **Local conversation state** | Current conversation ID, message history (for display) |
| **Backend connectivity** | Configurable base URL/endpoint, streaming (NDJSON) and non-streaming HTTP support |
| **Styling and extension** | Themeable via tokens/CSS variables, component boundaries that allow future panels without refactor |

### Out of Scope (Explicitly)

- Any decision about what context to send
- Any knowledge of LLMs/models/agents/tools
- Any orchestration or graph execution
- Any direct writes to Mimir / knowledge store
- Authentication/authorization beyond passing an opaque token (optional)

---

## 2. Users and Use Cases

### Primary User Stories (V1)

| Story | Description |
|-------|-------------|
| **Send a message** | Type text, press Enter/click Send |
| **View responses** | See assistant responses appended in order |
| **Streaming** | See response appear incrementally as it arrives |
| **Stop streaming** | User can stop an in-progress response (client-side abort) |
| **Retry** | Retry the last request if it fails |
| **Start new conversation** | Clears visible message state and begins a new thread |
| **Copy message** | Copy assistant/user message text (basic usability) |

### Developer Stories (V1)

| Story | Description |
|-------|-------------|
| **Configure backend** | Set endpoint via config/env |
| **Works with echo server** | Runs against a dummy backend that implements the protocol |
| **Swap backend without UI code changes** | Only configuration changes required |

---

## 3. UI/UX Requirements

### Core Layout

#### Chat Transcript Panel
- Chronological messages
- Clearly differentiated roles (user vs assistant)

#### Composer Panel
- Multiline input
- Send button
- Optional stop button during streaming

#### Status Indicators
- "streaming…" / "error" / "disconnected"

### Interaction Rules

| Action | Behavior |
|--------|----------|
| **Enter** | Sends message |
| **Shift+Enter** | Inserts newline |
| **While streaming** | Input remains editable (preferred) but Send is disabled, OR Send triggers "stop then send" |
| **Stop button** | Terminates current stream cleanly |
| **On error** | Show visible error state tied to the failed assistant message; show "Retry" action |

### Accessibility

- Keyboard navigable
- Visible focus states
- Screen-reader friendly labeling of input/buttons
- Reasonable contrast and font sizing

---

## 4. Data Model (Client-Side)

### Conversation State (V1)

```typescript
interface ConversationState {
  conversation_id: string | null;
  messages: Message[];
  pending_request_id: string | null;
  last_error?: Error;
}

interface Message {
  message_id: string;           // client-generated placeholder allowed
  role: "user" | "assistant";
  content: string;
  status: "final" | "streaming" | "error" | "interrupted";
  created_at?: string;          // optional
}
```

### Persistence (V1)

**Not required.**

> Optional: localStorage cache is allowed but must not be treated as canonical.

---

## 5. Backend Interface Requirements (Chat UI Contract)

The Chat UI speaks a single protocol to a backend endpoint. It does not interpret semantics; it only renders.

### Transport Modes

1. **Non-streaming HTTP response** (JSON)
2. **Streaming via Streamable HTTP** (NDJSON) — primary
3. **Streaming via Server-Sent Events** (SSE) — optional fallback

> **See:** [Protocol Design](protocol_design.md) for detailed transport analysis and rationale.

### Request Envelope (UI → Backend)

```json
{
  "request_id": "uuid-string",
  "conversation_id": "optional-string",
  "message": {
    "role": "user",
    "content": "string"
  },
  "metadata": {}
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `request_id` | ✓ | Client-generated UUID |
| `conversation_id` | | Optional, omit for new conversations |
| `message.role` | ✓ | Always `"user"` |
| `message.content` | ✓ | User's message text |
| `metadata` | | Opaque JSON (e.g., `{ "stream": true }`) |
| `auth_token` | | Not in body; passed as header if used |

### Non-Streaming Response (Backend → UI)

```json
{
  "conversation_id": "string",
  "message": {
    "role": "assistant",
    "content": "string",
    "message_id": "optional-string"
  },
  "metadata": {},
  "warnings": []
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `conversation_id` | ✓ | String identifier |
| `message.role` | ✓ | Always `"assistant"` |
| `message.content` | ✓ | Response text |
| `message.message_id` | | Optional |
| `metadata` | | Opaque |
| `warnings` | | Optional array |

### Streaming Response (SSE)

#### Event Types

| Event | Payload | Description |
|-------|---------|-------------|
| `message.start` | `{ conversation_id, message_id }` | Stream begins |
| `message.delta` | `{ delta: string }` | Incremental content chunk |
| `message.done` | `{}` | Stream complete (optional metadata allowed) |
| `error` | `{ code, message }` | Error occurred |

#### Client Requirements

- Append delta chunks to the currently streaming assistant message
- Mark message `final` on `done`
- Mark message `error` on `error`
- Support aborting an in-flight stream (client-side cancel)

---

## 6. Configuration Requirements

| Setting | Required | Description |
|---------|----------|-------------|
| Backend base URL | ✓ | Root URL for API calls |
| Endpoint path | ✓ | Path to chat endpoint |
| Streaming on/off | | May be configurable |
| Auth header | | Optional opaque bearer token |

---

## 7. Extensibility Requirements (V1)

The UI must be structured to allow later additions without refactoring core message flow:

- **Optional secondary panel area** — collapsed by default
- **Message metadata rendering hook** — display-only; no logic
- **Replaceable transport/client layer** — NDJSON now; other protocols later
- **Rich media rendering** — Plan for images and other media in future

---

## 8. Acceptance Criteria (V1)

- [ ] Works end-to-end with an echo server implementing the contract
- [ ] Streaming renders incrementally and can be stopped
- [ ] Conversation ID is tracked and reused in subsequent sends
- [ ] Errors surface clearly and allow retry
- [ ] Styling can be changed via a small set of theme variables/tokens
- [ ] Backend can be swapped via configuration only

---

---

## Related Documents

- **[Protocol Design](protocol_design.md)** — Streaming transport analysis and protocol specification
- **[Design Decisions](design_decisions.md)** — Architectural decision log
- **[Textual Implementation](implementations/textual/technical_design.md)** — Terminal UI technical design
- **[Echo Server](echo-server/technical_design.md)** — Test server technical design
