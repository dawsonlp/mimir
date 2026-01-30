"""Chat Echo Server - FastAPI app with LLM and Mimir integration."""

import json
import os
import uuid
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse

from .llm import stream_chat
from .mimir_client import get_mimir_client

# Load environment variables
load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    mimir = get_mimir_client()
    mimir_available = await mimir.health_check()
    llm_model = os.getenv("LLM_MODEL", "ollama:llama3.2")
    
    print(f"Chat Echo Server starting...")
    print(f"  LLM Model: {llm_model}")
    print(f"  Mimir: {'connected' if mimir_available else 'NOT AVAILABLE'}")
    
    if not mimir_available:
        print("  WARNING: Mimir not available, conversations will not be persisted")
    
    yield
    
    # Shutdown
    await mimir.close()


app = FastAPI(
    title="Chat Echo Server",
    description="Chat server with LLM and Mimir integration",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    mimir = get_mimir_client()
    mimir_available = await mimir.health_check()
    
    return {
        "status": "ok",
        "mimir": "connected" if mimir_available else "unavailable",
        "llm_model": os.getenv("LLM_MODEL", "ollama:llama3.2"),
    }


@app.post("/v1/chat")
async def chat(request: Request):
    """Chat endpoint - accepts message, returns streaming LLM response.
    
    Request body:
        {
            "conversation_id": "optional-existing-id",
            "message": {
                "role": "user",
                "content": "Hello!"
            }
        }
    
    Response: NDJSON stream with message.start, message.delta, message.done events
    """
    body = await request.json()
    
    conversation_id = body.get("conversation_id")
    message = body.get("message", {})
    user_content = message.get("content", "")
    
    mimir = get_mimir_client()
    mimir_available = await mimir.health_check()
    
    async def generate():
        nonlocal conversation_id
        
        # Convert conversation_id to int if provided (Mimir uses integer IDs)
        conv_id_int: int | None = None
        if conversation_id and mimir_available:
            try:
                conv_id_int = int(conversation_id)
                # Check if conversation exists
                exists = await mimir.conversation_exists(conv_id_int)
                if not exists:
                    conv_id_int = await mimir.create_conversation()
            except ValueError:
                # Invalid ID format, create new
                conv_id_int = await mimir.create_conversation()
        elif not conversation_id and mimir_available:
            # Create new conversation
            conv_id_int = await mimir.create_conversation()
        
        # Set conversation_id for protocol (always string)
        if conv_id_int is not None:
            conversation_id = str(conv_id_int)
        elif not conversation_id:
            # No Mimir, generate local ID
            conversation_id = str(uuid.uuid4())
        
        # Get conversation history from Mimir
        messages = []
        if mimir_available and conv_id_int is not None:
            try:
                messages = await mimir.get_conversation_messages(conv_id_int)
            except Exception:
                pass  # Start fresh if history unavailable
        
        # Add current user message
        messages.append({"role": "user", "content": user_content})
        
        # Save user message to Mimir
        if mimir_available and conv_id_int is not None:
            try:
                await mimir.add_message(conv_id_int, "user", user_content)
            except Exception as e:
                print(f"Warning: Failed to save user message to Mimir: {e}")
        
        # Generate message ID
        message_id = str(uuid.uuid4())[:8]
        
        # Emit message.start
        start_event = {
            "type": "message.start",
            "conversation_id": conversation_id,
            "message_id": message_id,
        }
        yield json.dumps(start_event) + "\n"
        
        # Stream LLM response
        full_response = ""
        try:
            async for chunk in stream_chat(messages):
                full_response += chunk
                delta_event = {
                    "type": "message.delta",
                    "delta": chunk,
                }
                yield json.dumps(delta_event) + "\n"
        except Exception as e:
            # Emit error event
            error_event = {
                "type": "error",
                "code": "llm_error",
                "message": str(e),
            }
            yield json.dumps(error_event) + "\n"
            return
        
        # Save assistant response to Mimir
        if mimir_available and conv_id_int is not None and full_response:
            try:
                await mimir.add_message(conv_id_int, "assistant", full_response)
            except Exception as e:
                print(f"Warning: Failed to save assistant message to Mimir: {e}")
        
        # Emit message.done
        done_event = {
            "type": "message.done",
        }
        yield json.dumps(done_event) + "\n"
    
    return StreamingResponse(
        generate(),
        media_type="application/x-ndjson",
    )


def main():
    """Run the server."""
    import uvicorn
    
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8001"))
    
    uvicorn.run(
        "src.server:app",
        host=host,
        port=port,
        reload=True,
    )


if __name__ == "__main__":
    main()