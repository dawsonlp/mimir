# Chat UI Protocol Design

This document analyzes streaming transport options and defines the protocol contract for the Chat UI.

---

## 1. Streaming Transport Analysis

### Options Comparison

| Protocol | Browser Support | Proxy Compatibility | Direction | Reconnection | Complexity |
|----------|-----------------|---------------------|-----------|--------------|------------|
| **SSE (Server-Sent Events)** | Native `EventSource` API | Moderate — some proxies buffer | Server → Client only | Built-in automatic | Low |
| **Streamable HTTP (NDJSON)** | `fetch()` + `ReadableStream` | High — standard HTTP | Server → Client | Manual implementation | Low-Medium |
| **WebSocket** | Native `WebSocket` API | Lower — requires upgrade | Bidirectional | Manual implementation | Medium |

### SSE (Server-Sent Events)

**How it works:**
```
GET /chat/stream
Accept: text/event-stream

event: message.start
data: {"conversation_id":"abc","message_id":"123"}

event: message.delta
data: {"delta":"Hello"}

event: message.delta
data: {"delta":" world"}

event: message.done
data: {}
```

**Pros:**
- Native browser API (`EventSource`) with minimal code
- Built-in reconnection with `Last-Event-ID`
- Named event types for clean dispatch
- Widely understood pattern

**Cons:**
- One-way only (client can't send mid-stream)
- Some corporate proxies/CDNs buffer SSE incorrectly
- `EventSource` API is limited (no custom headers without polyfill)
- Must use `fetch()` for POST + SSE, losing some native benefits

### Streamable HTTP (NDJSON)

**How it works:**
```
POST /chat
Content-Type: application/json
Accept: application/x-ndjson

{"request_id":"...","message":{...}}

---Response (chunked)---
{"type":"message.start","conversation_id":"abc","message_id":"123"}
{"type":"message.delta","delta":"Hello"}
{"type":"message.delta","delta":" world"}
{"type":"message.done"}
```

**Pros:**
- Standard HTTP POST — works through all proxies
- Aligns with MCP (Model Context Protocol) streaming
- Single request-response cycle (no separate SSE connection)
- Custom headers work naturally
- Can use same endpoint for streaming and non-streaming (content negotiation)

**Cons:**
- No native streaming API — requires manual `ReadableStream` handling
- No built-in reconnection
- Must parse line-by-line manually

### WebSocket

**How it works:**
```
ws://host/chat

→ {"type":"send","request_id":"...","message":{...}}
← {"type":"message.start","conversation_id":"abc"}
← {"type":"message.delta","delta":"Hello"}
← {"type":"message.done"}
```

**Pros:**
- True bidirectional communication
- Low latency for interactive use cases
- Single persistent connection

**Cons:**
- Overkill for request-response chat (we don't need client→server mid-stream)
- More complex connection lifecycle management
- Some proxies/load balancers require special configuration
- Not RESTful — harder to debug, cache, or load balance

---

## 2. Recommendation

### Primary: Streamable HTTP (NDJSON)

**Rationale:**
1. **Proxy compatibility** — Works through all standard HTTP infrastructure
2. **MCP alignment** — Matches the streaming approach used by MCP, enabling future interoperability
3. **Simplicity** — Single endpoint handles both streaming and non-streaming via `Accept` header
4. **Flexibility** — POST request naturally carries the full message payload with headers

### Fallback: SSE (Optional)

Keep SSE as an alternative for backends that prefer it. The event contract remains the same; only the wire format differs.

### Not Recommended: WebSocket

WebSocket is unnecessary complexity for this use case. Chat is fundamentally request-response with streaming response — bidirectional communication is not needed.

---

## 3. Protocol Contract (Transport-Agnostic)

The Chat UI defines an **event contract** independent of wire format. Both SSE and Streamable HTTP can implement this contract.

### Event Types

| Event | Payload | Description |
|-------|---------|-------------|
| `message.start` | `{ conversation_id, message_id }` | Stream begins; provides identifiers |
| `message.delta` | `{ delta: string }` | Incremental content chunk |
| `message.done` | `{ metadata? }` | Stream complete |
| `error` | `{ code, message, retryable? }` | Error occurred |

### Request Format

```typescript
interface ChatRequest {
  request_id: string;           // Client-generated UUID
  conversation_id?: string;     // Omit for new conversation
  message: {
    role: "user";
    content: string;
  };
  metadata?: Record<string, unknown>;  // Opaque pass-through
}
```

### Wire Format: Streamable HTTP (NDJSON)

**Request:**
```http
POST /v1/chat
Content-Type: application/json
Accept: application/x-ndjson
Authorization: Bearer <token>  (optional)

{
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "conversation_id": "conv-123",
  "message": {
    "role": "user",
    "content": "Hello, assistant"
  }
}
```

**Response (streaming):**
```http
HTTP/1.1 200 OK
Content-Type: application/x-ndjson
Transfer-Encoding: chunked

{"type":"message.start","conversation_id":"conv-123","message_id":"msg-456"}
{"type":"message.delta","delta":"Hello"}
{"type":"message.delta","delta":"! How can I help you today?"}
{"type":"message.done","metadata":{}}
```

**Response (non-streaming):**
```http
POST /v1/chat
Accept: application/json

HTTP/1.1 200 OK
Content-Type: application/json

{
  "conversation_id": "conv-123",
  "message": {
    "role": "assistant",
    "content": "Hello! How can I help you today?",
    "message_id": "msg-456"
  }
}
```

### Wire Format: SSE (Alternative)

**Request:**
```http
POST /v1/chat/stream
Content-Type: application/json
Accept: text/event-stream

{ ... same as above ... }
```

**Response:**
```http
HTTP/1.1 200 OK
Content-Type: text/event-stream
Cache-Control: no-cache

event: message.start
data: {"conversation_id":"conv-123","message_id":"msg-456"}

event: message.delta
data: {"delta":"Hello"}

event: message.delta
data: {"delta":"! How can I help you today?"}

event: message.done
data: {}
```

---

## 4. Content Negotiation Strategy

The backend can support both formats on the same endpoint using the `Accept` header:

| Accept Header | Response Format |
|---------------|-----------------|
| `application/json` | Single JSON response (non-streaming) |
| `application/x-ndjson` | Newline-delimited JSON (streaming) |
| `text/event-stream` | SSE format (streaming, alternative) |

This allows the Chat UI to:
1. Default to Streamable HTTP for best compatibility
2. Fall back to SSE if configured
3. Use non-streaming for simple testing

---

## 5. Client Implementation Notes

### Streamable HTTP Parsing

```typescript
async function* streamChat(request: ChatRequest): AsyncGenerator<StreamEvent> {
  const response = await fetch('/v1/chat', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Accept': 'application/x-ndjson',
    },
    body: JSON.stringify(request),
    signal: abortController.signal,  // For cancellation
  });

  const reader = response.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop()!;  // Keep incomplete line in buffer

    for (const line of lines) {
      if (line.trim()) {
        yield JSON.parse(line) as StreamEvent;
      }
    }
  }
}
```

### Cancellation

Both transports support client-initiated cancellation:
- **Streamable HTTP:** `AbortController.abort()`
- **SSE:** `EventSource.close()` or `AbortController` with fetch-based SSE

---

## 6. Error Handling

### Error Event Format

```typescript
interface ErrorEvent {
  type: "error";
  code: string;           // e.g., "rate_limited", "internal_error"
  message: string;        // Human-readable description
  retryable?: boolean;    // Hint for client retry logic
}
```

### HTTP Status Codes

| Status | Meaning | Client Action |
|--------|---------|---------------|
| 200 | Success (even if error event in stream) | Process stream |
| 400 | Bad request | Show error, don't retry |
| 401 | Unauthorized | Prompt for auth |
| 429 | Rate limited | Show error, retry with backoff |
| 500+ | Server error | Show error, allow retry |

---

## 7. Decision Summary

| Aspect | Decision |
|--------|----------|
| **Primary streaming transport** | Streamable HTTP (NDJSON) |
| **Fallback transport** | SSE (optional, same event contract) |
| **Not using** | WebSocket (unnecessary for this use case) |
| **Content negotiation** | Via `Accept` header |
| **Cancellation** | `AbortController` |
| **Error handling** | In-stream `error` event + HTTP status codes |

---

## 8. Open Questions

1. **Should the echo server implement both formats?** — Recommend yes for testing flexibility
2. **Connection timeout / keep-alive semantics?** — Defer to HTTP defaults
3. **Maximum message size limits?** — Define in backend, UI just renders
4. **Retry semantics for partial streams?** — Client responsibility; backend should support idempotent request_id

---

## References

- [MCP Specification — Streamable HTTP](https://modelcontextprotocol.io/)
- [WHATWG Streams API](https://streams.spec.whatwg.org/)
- [Server-Sent Events Spec](https://html.spec.whatwg.org/multipage/server-sent-events.html)
- [NDJSON Specification](http://ndjson.org/)