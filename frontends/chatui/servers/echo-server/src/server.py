"""
Echo Server - Protocol-compliant test server for Chat UI implementations.

Implements the chat protocol from protocol_design.md:
- POST /v1/chat with content negotiation
- Streaming via NDJSON (application/x-ndjson)
- Streaming via SSE (text/event-stream)
- Non-streaming JSON response
"""

import asyncio
import json
import uuid
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

app = FastAPI(
    title="Chat Echo Server",
    description="Protocol-compliant echo server for testing Chat UI implementations",
    version="0.1.0",
)

# Maximum bytes per delta chunk before splitting (for very large responses)
MAX_DELTA_SIZE = 64 * 1024  # 64KB


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok", "service": "echo-server"}


@app.post("/v1/chat")
async def chat(request: Request):
    """
    Main chat endpoint with content negotiation.
    
    Supports:
    - Accept: application/json → Single JSON response
    - Accept: application/x-ndjson → Streaming NDJSON
    - Accept: text/event-stream → Streaming SSE
    """
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
            headers={"Cache-Control": "no-cache"},
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
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        })


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
        # Chunk at MAX_DELTA_SIZE boundaries for very large content
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
        # Chunk at MAX_DELTA_SIZE boundaries for very large content
        for i in range(0, len(content), MAX_DELTA_SIZE):
            yield f"event: message.delta\n"
            yield f"data: {json.dumps({'delta': content[i:i + MAX_DELTA_SIZE]})}\n\n"
    
    # Done event
    yield f"event: message.done\n"
    yield f"data: {{}}\n\n"


async def stream_error(conversation_id: str, message_id: str):
    """Stream an error event for testing."""
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
    
    elif command == "/empty":
        return JSONResponse({
            "conversation_id": conversation_id,
            "message": {
                "role": "assistant",
                "content": "",
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)