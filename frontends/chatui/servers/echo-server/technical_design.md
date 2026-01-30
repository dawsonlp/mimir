# Echo Server — Technical Design

This document describes the technical architecture for the protocol-compliant echo server used for testing Chat UI implementations.

---

## 1. Overview

A minimal HTTP server that:
- Implements the chat protocol from `protocol_design.md`
- Echoes user messages back as assistant responses
- Supports both streaming (NDJSON) and non-streaming (JSON) modes
- Sends content efficiently (single delta for typical messages)
- Provides error simulation for testing error handling

---

## 2. Technology Stack

| Component | Technology | Version |
|-----------|------------|---------|
| **Framework** | FastAPI | 0.115+ |
| **ASGI Server** | Uvicorn | 0.34+ |
| **Python** | Python | 3.13.x |
| **Package Manager** | Poetry | Latest |

---

## 3. API Endpoints

### 3.1 Chat Endpoint

```
POST /v1/chat
```

**Request:**
```json
{
  "request_id": "uuid-string",
  "conversation_id": "optional-string",
  "message": {
    "role": "user",
    "content": "Hello, echo server!"
  },
  "metadata": {}
}
```

**Content Negotiation:**

| Accept Header | Response Format |
|---------------|-----------------|
| `application/json` | Single JSON response |
| `application/x-ndjson` | Streaming NDJSON |
| `text/event-stream` | Streaming SSE (optional) |

---

## 4. Response Formats

### 4.1 Non-Streaming (JSON)

When `Accept: application/json`:

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "conversation_id": "conv-abc123",
  "message": {
    "role": "assistant",
    "content": "Echo: Hello, echo server!",
    "message_id": "msg-xyz789"
  },
  "metadata": {
    "echo_server": true,
    "timestamp": "2025-01-07T19:00:00Z"
  }
}
```

### 4.2 Streaming (NDJSON)

When `Accept: application/x-ndjson`:

```http
HTTP/1.1 200 OK
Content-Type: application/x-ndjson
Transfer-Encoding: chunked

{"type":"message.start","conversation_id":"conv-abc123","message_id":"msg-xyz789"}
{"type":"message.delta","delta":"Echo: Hello, echo server!"}
{"type":"message.done","metadata":{"echo_server":true}}
```

### 4.3 Streaming (SSE) — Optional

When `Accept: text/event-stream`:

```http
HTTP/1.1 200 OK
Content-Type: text/event-stream
Cache-Control: no-cache

event: message.start
data: {"conversation_id":"conv-abc123","message_id":"msg-xyz789"}

event: message.delta
data: {"delta":"Echo: Hello, echo server!"}

event: message.done
data: {}
```

---

## 5. Echo Behavior

### Default Echo

The server echoes the user's message with a prefix:

```
User: "Hello, world!"
Assistant: "Echo: Hello, world!"
```

### Chunking Strategy

The echo server sends content efficiently:
- **Single delta** for typical messages (under 64KB)
- **Multiple deltas** only for very large content (chunked at 64KB boundaries)

This reflects how a real backend would forward LLM output: send what you have when you have it, without artificial delays or word-by-word splitting.

```python
# Maximum bytes per delta chunk before splitting
MAX_DELTA_SIZE = 64 * 1024  # 64KB

async def stream_ndjson(conversation_id, message_id, content):
    yield {"type": "message.start", ...}
    
    if len(content) <= MAX_DELTA_SIZE:
        yield {"type": "message.delta", "delta": content}
    else:
        for i in range(0, len(content), MAX_DELTA_SIZE):
            yield {"type": "message.delta", "delta": content[i:i + MAX_DELTA_SIZE]}
    
    yield {"type": "message.done", ...}
```

---

## 6. Special Commands

The echo server recognizes special commands for testing:

| User Message | Behavior |
|--------------|----------|
| `/error` | Returns an error event |
| `/error-http` | Returns HTTP 500 status |
| `/slow` | Adds 2s delay before responding |
| `/long` | Returns a very long response (for scroll testing) |
| `/empty` | Returns empty content |

### Error Simulation

```
User: "/error"
```

**NDJSON Response:**
```json
{"type":"message.start","conversation_id":"conv-abc123","message_id":"msg-xyz789"}
{"type":"error","code":"simulated_error","message":"This is a simulated error for testing"}
```

**HTTP Error:**
```
User: "/error-http"
```
```http
HTTP/1.1 500 Internal Server Error
Content-Type: application/json

{
  "error": {
    "code": "internal_error",
    "message": "Simulated HTTP error"
  }
}
```

---

## 7. Conversation Management

### ID Generation

- If `conversation_id` is provided, it's reused
- If omitted, server generates: `conv-{uuid4()[:8]}`
- Message IDs are always generated: `msg-{uuid4()[:8]}`

### No State Persistence

The echo server is stateless:
- No conversation history stored
- Each request is independent
- Conversation IDs are for protocol compliance only

---

## 8. Implementation

### Main Application

```python
from fastapi import FastAPI, Request, Response
from fastapi.responses import StreamingResponse, JSONResponse
import asyncio
import uuid
import json
from datetime import datetime

app = FastAPI(title="Chat Echo Server")

@app.post("/v1/chat")
async def chat(request: Request):
    body = await request.json()
    accept = request.headers.get("accept", "application/json")
    
    # Extract request data
    request_id = body.get("request_id", str(uuid.uuid4()))
    conversation_id = body.get("conversation_id") or f"conv-{uuid.uuid4().hex[:8]}"
    user_content = body.get("message", {}).get("content", "")
    
    # Check for special commands
    if user_content.startswith("/"):
        return await handle_command(user_content, conversation_id, accept)
    
    # Generate echo response
    echo_content = f"Echo: {user_content}"
    message_id = f"msg-{uuid.uuid4().hex[:8]}"
    
    if "application/x-ndjson" in accept:
        return StreamingResponse(
            stream_ndjson(conversation_id, message_id, echo_content),
            media_type="application/x-ndjson",
        )
    elif "text/event-stream" in accept:
        return StreamingResponse(
            stream_sse(conversation_id, message_id, echo_content),
            media_type="text/event-stream",
        )
    else:
        return JSONResponse({
            "conversation_id": conversation_id,
            "message": {
                "role": "assistant",
                "content": echo_content,
                "message_id": message_id,
            },
            "metadata": {
                "echo_server": True,
                "timestamp": datetime.utcnow().isoformat() + "Z",
            },
        })
```

### NDJSON Streaming

```python
# Maximum bytes per delta chunk before splitting
MAX_DELTA_SIZE = 64 * 1024  # 64KB

async def stream_ndjson(
    conversation_id: str,
    message_id: str,
    content: str,
):
    """Stream response as newline-delimited JSON.
    
    Sends content in a single delta for typical messages.
    Only chunks at MAX_DELTA_SIZE boundaries for very large responses.
    """
    
    # Start event
    yield json.dumps({
        "type": "message.start",
        "conversation_id": conversation_id,
        "message_id": message_id,
    }) + "\n"
    
    # Delta event(s) - single chunk unless content exceeds MAX_DELTA_SIZE
    if len(content) <= MAX_DELTA_SIZE:
        yield json.dumps({
            "type": "message.delta",
            "delta": content,
        }) + "\n"
    else:
        for i in range(0, len(content), MAX_DELTA_SIZE):
            yield json.dumps({
                "type": "message.delta",
                "delta": content[i:i + MAX_DELTA_SIZE],
            }) + "\n"
    
    # Done event
    yield json.dumps({
        "type": "message.done",
        "metadata": {"echo_server": True},
    }) + "\n"
```

### SSE Streaming

```python
async def stream_sse(
    conversation_id: str,
    message_id: str,
    content: str,
):
    """Stream response as Server-Sent Events.
    
    Sends content in a single delta for typical messages.
    Only chunks at MAX_DELTA_SIZE boundaries for very large responses.
    """
    
    # Start event
    yield f"event: message.start\n"
    yield f"data: {json.dumps({'conversation_id': conversation_id, 'message_id': message_id})}\n\n"
    
    # Delta event(s) - single chunk unless content exceeds MAX_DELTA_SIZE
    if len(content) <= MAX_DELTA_SIZE:
        yield f"event: message.delta\n"
        yield f"data: {json.dumps({'delta': content})}\n\n"
    else:
        for i in range(0, len(content), MAX_DELTA_SIZE):
            yield f"event: message.delta\n"
            yield f"data: {json.dumps({'delta': content[i:i + MAX_DELTA_SIZE]})}\n\n"
    
    # Done event
    yield f"event: message.done\n"
    yield f"data: {{}}\n\n"
```

### Command Handler

```python
async def handle_command(
    command: str,
    conversation_id: str,
    accept: str,
):
    """Handle special test commands."""
    
    message_id = f"msg-{uuid.uuid4().hex[:8]}"
    
    if command == "/error":
        if "application/x-ndjson" in accept:
            return StreamingResponse(
                stream_error(conversation_id, message_id),
                media_type="application/x-ndjson",
            )
        # Non-streaming: use HTTP status code for errors (per protocol)
        return JSONResponse(
            {"error": {"code": "simulated_error", "message": "Simulated error"}},
            status_code=500,
        )
    
    elif command == "/error-http":
        return JSONResponse(
            {"error": {"code": "internal_error", "message": "Simulated HTTP error"}},
            status_code=500,
        )
    
    elif command == "/slow":
        await asyncio.sleep(2)
        return JSONResponse({
            "conversation_id": conversation_id,
            "message": {
                "role": "assistant",
                "content": "This response was delayed by 2 seconds.",
                "message_id": message_id,
            },
        })
    
    elif command == "/long":
        long_content = "This is a very long response. " * 50
        if "application/x-ndjson" in accept:
            return StreamingResponse(
                stream_ndjson(conversation_id, message_id, long_content),
                media_type="application/x-ndjson",
            )
        return JSONResponse({
            "conversation_id": conversation_id,
            "message": {
                "role": "assistant",
                "content": long_content,
                "message_id": message_id,
            },
        })
    
    else:
        return JSONResponse({
            "conversation_id": conversation_id,
            "message": {
                "role": "assistant",
                "content": f"Unknown command: {command}",
                "message_id": message_id,
            },
        })


async def stream_error(conversation_id: str, message_id: str):
    """Stream an error event."""
    yield json.dumps({
        "type": "message.start",
        "conversation_id": conversation_id,
        "message_id": message_id,
    }) + "\n"
    
    yield json.dumps({
        "type": "error",
        "code": "simulated_error",
        "message": "This is a simulated error for testing",
    }) + "\n"
```

---

## 9. Health Check

```python
@app.get("/health")
async def health():
    return {"status": "ok", "service": "echo-server"}
```

---

## 10. Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | `8000` | Server port |
| `HOST` | `0.0.0.0` | Server host |
| `LOG_LEVEL` | `info` | Logging level |

### Running the Server

```bash
# Development
uvicorn src.server:app --reload --port 8000

# Production
uvicorn src.server:app --host 0.0.0.0 --port 8000
```

---

## 11. File Structure

```
echo-server/
├── technical_design.md      # This document
├── pyproject.toml           # Poetry project config
├── src/
│   ├── __init__.py
│   ├── server.py            # FastAPI application
│   ├── streaming.py         # NDJSON and SSE generators
│   └── commands.py          # Special command handlers
└── tests/
    ├── __init__.py
    ├── test_chat.py         # Chat endpoint tests
    ├── test_streaming.py    # Streaming format tests
    └── test_commands.py     # Special command tests
```

---

## 12. Dependencies

```toml
[tool.poetry.dependencies]
python = "^3.13"
fastapi = "^0.115"
uvicorn = "^0.34"

[tool.poetry.group.dev.dependencies]
pytest = "^8.0"
pytest-asyncio = "^0.24"
httpx = "^0.28"
```

---

## 13. Testing with curl

### Non-streaming

```bash
curl -X POST http://localhost:8000/v1/chat \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{"message": {"role": "user", "content": "Hello!"}}'
```

### Streaming (NDJSON)

```bash
curl -X POST http://localhost:8000/v1/chat \
  -H "Content-Type: application/json" \
  -H "Accept: application/x-ndjson" \
  -d '{"message": {"role": "user", "content": "Hello!"}}'
```

### Error Simulation

```bash
curl -X POST http://localhost:8000/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message": {"role": "user", "content": "/error"}}'
```

---

## 14. Docker Support (Optional)

```dockerfile
FROM python:3.13-slim

WORKDIR /app
COPY pyproject.toml poetry.lock ./
RUN pip install poetry && poetry install --no-dev

COPY src/ ./src/
EXPOSE 8000

CMD ["poetry", "run", "uvicorn", "src.server:app", "--host", "0.0.0.0", "--port", "8000"]
```

---

## 15. Acceptance Criteria

- [ ] Responds to POST /v1/chat with JSON
- [ ] Streams NDJSON when Accept header requests it
- [ ] Streams SSE when Accept header requests it
- [ ] Generates conversation_id if not provided
- [ ] Sends content in single delta for typical messages
- [ ] `/error` command triggers error event
- [ ] `/error-http` returns HTTP 500
- [ ] `/slow` delays response by 2 seconds
- [ ] `/long` returns long content for scroll testing
- [ ] Health check endpoint works
