# Mimir Chat UI

A terminal-based chat interface built with Textual, connecting to LLM backends with Mimir persistence.

## Quick Start

### Prerequisites

- Python 3.13+
- [Ollama](https://ollama.ai) installed and running
- [Mimir](https://github.com/dawsonlp/mimir) running on port 38000

### 1. Install Ollama and pull a model

```bash
# Install Ollama from https://ollama.ai
ollama pull llama3.2
```

### 2. Set up the Chat Server

```bash
cd servers/chat_echo_server

# Install dependencies
pip install -e .

# Create config (edit if needed)
cp .env.example .env
```

The default config uses Ollama with llama3.2. Edit `.env` to change models or providers.

### 3. Set up the Chat UI

```bash
cd implementations/textual

# Install dependencies
poetry install
```

### 4. Run!

**Terminal 1 - Start the server:**
```bash
cd servers/chat_echo_server
uvicorn src.server:app --reload --port 8001
```

**Terminal 2 - Start the UI:**
```bash
cd implementations/textual
poetry run python -m src.chat_app --backend-url http://localhost:8001
```

You'll see:
- A terminal chat interface
- Status bar showing `● Ready │ http://localhost:8001`
- Type a message and press Enter to chat with the LLM!

---

## Architecture

```
┌─────────────────────┐     ┌─────────────────────┐     ┌─────────────┐
│   Textual Chat UI   │────▶│  Chat Echo Server   │────▶│ Ollama/Claude│
│   (Terminal TUI)    │◀────│  (FastAPI/8001)     │     └─────────────┘
└─────────────────────┘     │                     │────▶┌─────────────┐
                            └─────────────────────┘     │    Mimir    │
                                                        └─────────────┘
```

## Components

| Component | Location | Purpose |
|-----------|----------|---------|
| **Chat UI** | `implementations/textual/` | Terminal chat interface |
| **Chat Server** | `servers/chat_echo_server/` | LLM + Mimir integration |
| **Echo Server** | `servers/echo-server/` | Simple test server (no LLM) |

## Configuration

### Switching LLM Providers

Edit `servers/chat_echo_server/.env`:

```bash
# Ollama (local, default)
LLM_MODEL=ollama:llama3.2

# Anthropic Claude
LLM_MODEL=anthropic:claude-sonnet-4-5
ANTHROPIC_API_KEY=sk-ant-...

# OpenAI
LLM_MODEL=openai:gpt-4o
OPENAI_API_KEY=sk-...
```

### Mimir Persistence

Conversations are automatically saved to Mimir as artifacts:
- Each conversation becomes a "conversation" artifact
- Each message becomes a child "message" artifact
- History is loaded when continuing a conversation

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `Enter` | Send message |
| `Shift+Enter` | New line in message |
| `Escape` | Stop streaming response |
| `Ctrl+N` | New conversation |
| `Ctrl+C` | Quit |

## Transcript Logging

Save conversations to a file:

```bash
# Markdown format
poetry run python -m src.chat_app --backend-url http://localhost:8001 chat.md

# JSON format
poetry run python -m src.chat_app --backend-url http://localhost:8001 chat.json
```

## Testing with Echo Server

For UI development without an LLM:

```bash
# Terminal 1
cd servers/echo-server && uvicorn src.server:app --reload --port 8000

# Terminal 2
cd implementations/textual
poetry run python -m src.chat_app --backend-url http://localhost:8000
```

The echo server mirrors your messages back (useful for testing streaming).

## Port Reference

| Service | Port |
|---------|------|
| Echo Server | 8000 |
| Chat Server | 8001 |
| Mimir | 38000 |

---

## Project Structure

```
frontends/chatui/
├── docs/
│   ├── README.md                # This file
│   ├── protocol_design.md       # Chat protocol specification
│   ├── design_decisions.md      # Architecture decisions
│   └── requirements.md          # Requirements specification
│
├── implementations/textual/     # Textual Chat UI
│   ├── src/
│   │   ├── chat_app.py         # Main application
│   │   ├── transport/          # HTTP client
│   │   └── widgets/            # UI components
│   └── pyproject.toml
│
├── servers/
│   ├── chat_echo_server/        # LLM Chat Server
│   │   ├── src/
│   │   │   ├── server.py       # FastAPI app
│   │   │   ├── llm.py          # Multi-provider LLM client
│   │   │   └── mimir_client.py # Mimir persistence
│   │   ├── .env.example
│   │   └── pyproject.toml
│   │
│   └── echo-server/             # Simple Echo Server (testing)
│       ├── src/server.py
│       └── pyproject.toml
│
└── middleware/                  # Middleware components