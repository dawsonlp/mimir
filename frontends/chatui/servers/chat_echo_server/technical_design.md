# Chat Echo Server - Technical Design

Chat server that implements the chat protocol with real LLM integration and Mimir persistence.

## Overview

Unlike the simple echo-server, this server:
1. Calls a real LLM (Ollama, Claude, or OpenAI)
2. Persists conversations to Mimir as artifacts
3. Maintains conversation history across messages

## Architecture

```
┌──────────────┐     ┌─────────────────────────────────────────────┐
│   Chat UI    │────▶│          Chat Echo Server                   │
│              │◀────│                                             │
└──────────────┘     │  ┌──────────┐  ┌─────────┐  ┌───────────┐  │
                     │  │ server.py│──│ llm.py  │──│ LLM API   │  │
                     │  │ (FastAPI)│  └─────────┘  └───────────┘  │
                     │  │          │                               │
                     │  │          │  ┌─────────────────┐         │
                     │  │          │──│ mimir_client.py │─────────┼──▶ Mimir
                     │  └──────────┘  └─────────────────┘         │
                     └─────────────────────────────────────────────┘
```

## Components

### server.py
- FastAPI application
- Implements `/v1/chat` endpoint (same protocol as echo-server)
- Coordinates LLM calls and Mimir persistence
- Streams NDJSON responses

### llm.py
- Multi-provider LLM client using LangChain
- Supports: Ollama, Anthropic Claude, OpenAI
- Provider selected via `LLM_MODEL` environment variable

### mimir_client.py
- Async HTTP client for Mimir API
- Creates conversation artifacts
- Stores messages as child artifacts
- Retrieves conversation history

## Configuration

Copy `.env.example` to `.env` and configure:

```bash
# Select active model (provider:model format)
LLM_MODEL=ollama:llama3.2

# Provider credentials
OLLAMA_BASE_URL=http://localhost:11434
ANTHROPIC_API_KEY=sk-ant-...

# Mimir connection
MIMIR_BASE_URL=http://localhost:38000
MIMIR_TENANT_ID=default
```

## Model Options

| Provider | Model Examples |
|----------|----------------|
| ollama | `ollama:llama3.2`, `ollama:mistral`, `ollama:codellama` |
| anthropic | `anthropic:claude-sonnet-4-5`, `anthropic:claude-opus-4-5` |
| openai | `openai:gpt-4`, `openai:gpt-4o` |

## Running

```bash
cd chat_echo_server

# Install dependencies
pip install -e .

# Copy and edit configuration
cp .env.example .env

# Run the server (development)
uvicorn src.server:app --reload --port 8001

# Run the server (production)
uvicorn src.server:app --host 0.0.0.0 --port 8001
```

Server starts at http://localhost:8001

## API Endpoints

### GET /health
Health check with Mimir and LLM status.

### POST /v1/chat
Send message, receive streaming LLM response.

**Request:**
```json
{
  "conversation_id": "optional-uuid",
  "message": {
    "role": "user",
    "content": "Hello!"
  }
}
```

**Response:** NDJSON stream
```json
{"type": "message.start", "conversation_id": "uuid", "message_id": "abc123"}
{"type": "message.delta", "delta": "Hello"}
{"type": "message.delta", "delta": "! How"}
{"type": "message.delta", "delta": " can I help?"}
{"type": "message.done"}
```

## Mimir Integration

### Conversation Structure
```
Artifact (conversation)
├── artifact_type: "conversation"
├── title: "Conversation 2026-01-07T..."
│
├── Child (message)
│   ├── artifact_type: "message"
│   ├── content: "Hello!"
│   └── metadata: {role: "user"}
│
└── Child (message)
    ├── artifact_type: "message"
    ├── content: "Hello! How can I help?"
    └── metadata: {role: "assistant"}
```

### Graceful Degradation
If Mimir is unavailable:
- Server still works
- Conversations not persisted
- History not maintained across restarts
- Warning logged on startup

## Testing with Ollama

1. Install Ollama: https://ollama.ai
2. Pull a model: `ollama pull llama3.2`
3. Set `LLM_MODEL=ollama:llama3.2` in `.env`
4. Run server: `uvicorn src.server:app --reload --port 8001`
5. Run UI pointing to port 8001:
   ```bash
   cd ../implementations/textual
   poetry run python -m src.chat_app --backend-url http://localhost:8001
   ```

## Testing with Claude

1. Get API key from https://console.anthropic.com
2. Set in `.env`:
   ```
   LLM_MODEL=anthropic:claude-sonnet-4-5
   ANTHROPIC_API_KEY=sk-ant-...
   ```
3. Run server: `uvicorn src.server:app --reload --port 8001`
4. Run UI:
   ```bash
   cd ../implementations/textual
   poetry run python -m src.chat_app --backend-url http://localhost:8001
   ```

## Port Allocation

| Server | Default Port |
|--------|--------------|
| echo-server | 8000 |
| chat_echo_server | 8001 |
| Mimir | 38000 |

The UI status bar shows the connected backend URL so you know which server you're talking to.
