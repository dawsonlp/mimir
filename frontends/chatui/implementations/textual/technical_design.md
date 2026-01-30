# Textual Chat UI — Technical Design

This document describes the technical architecture for the Textual-based Chat UI implementation.

---

## 1. Overview

A terminal-based chat interface built with [Textual](https://textual.textualize.io/) that:
- Runs in any terminal (macOS, Linux, Windows)
- Connects to a configurable HTTP backend
- Streams responses via NDJSON
- Can optionally deploy to browser via Textual Web

---

## 2. Technology Stack

| Component | Technology | Version |
|-----------|------------|---------|
| **UI Framework** | Textual | 3.x (latest) |
| **HTTP Client** | httpx | 0.28+ |
| **Python** | Python | 3.13.x |
| **Package Manager** | Poetry | Latest |
| **Styling** | TCSS (Textual CSS) | Built-in |

---

## 3. Architecture

### High-Level Structure

```
┌─────────────────────────────────────────────────────────┐
│                    ChatApp (Textual App)                │
│  ┌─────────────────────────────────────────────────┐    │
│  │              MessageList (VerticalScroll)       │    │
│  │  ┌─────────────────────────────────────────┐    │    │
│  │  │  ChatMessage (user)                     │    │    │
│  │  │  ChatMessage (assistant, streaming)     │    │    │
│  │  │  ChatMessage (assistant, final)         │    │    │
│  │  └─────────────────────────────────────────┘    │    │
│  └─────────────────────────────────────────────────┘    │
│  ┌─────────────────────────────────────────────────┐    │
│  │              Composer (Input + Buttons)         │    │
│  └─────────────────────────────────────────────────┘    │
│  ┌─────────────────────────────────────────────────┐    │
│  │              StatusBar (Footer)                 │    │
│  └─────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────┘
              ↓ events ↓           ↑ state updates ↑
┌─────────────────────────────────────────────────────────┐
│                   ChatClient (Transport)                │
│              httpx async streaming client               │
│                  → Backend HTTP API                     │
└─────────────────────────────────────────────────────────┘
```

### Layer Responsibilities

| Layer | Responsibility | Does NOT do |
|-------|----------------|-------------|
| **Widgets** | Render UI, emit user events | Make HTTP calls, manage state |
| **App** | Coordinate widgets, manage conversation state | Protocol details |
| **Transport** | HTTP client, NDJSON parsing, streaming | UI rendering |

---

## 4. Widget Design

### 4.1 ChatMessage

Renders a single message (user or assistant).

```python
class ChatMessage(Widget):
    """A single chat message with role and content."""
    
    role: Reactive[str]          # "user" | "assistant"
    content: Reactive[str]       # Message text (may update during streaming)
    status: Reactive[str]        # "final" | "streaming" | "error"
    
    def compose(self) -> ComposeResult:
        yield Static(self.role_label, classes="role")
        yield Markdown(self.content, classes="content")
        if self.status == "error":
            yield Button("Retry", id="retry")
```

**Styling classes:**
- `.message-user` — User message styling
- `.message-assistant` — Assistant message styling
- `.message-streaming` — Pulsing/animated indicator
- `.message-error` — Error state styling

### 4.2 MessageList

Container for all messages with auto-scroll.

```python
class MessageList(VerticalScroll):
    """Scrollable container for chat messages."""
    
    def add_message(self, message: MessageData) -> ChatMessage:
        widget = ChatMessage(message)
        self.mount(widget)
        self.scroll_end(animate=False)
        return widget
    
    def update_streaming(self, message_id: str, content: str) -> None:
        widget = self.query_one(f"#msg-{message_id}")
        widget.content = content
```

### 4.3 Composer

Input area with send/stop controls.

```python
class Composer(Widget):
    """Message input with send/stop buttons."""
    
    is_streaming: Reactive[bool] = False
    
    def compose(self) -> ComposeResult:
        yield TextArea(id="input", placeholder="Type a message...")
        with Horizontal(classes="buttons"):
            yield Button("Send", id="send", variant="primary")
            yield Button("Stop", id="stop", variant="warning")
    
    def watch_is_streaming(self, streaming: bool) -> None:
        self.query_one("#send").disabled = streaming
        self.query_one("#stop").display = streaming
```

**Keyboard bindings:**
- `Enter` — Send message (when not Shift)
- `Shift+Enter` — Insert newline
- `Escape` — Stop streaming (if active)

### 4.4 StatusBar

Connection and streaming status.

```python
class StatusBar(Static):
    """Shows connection status and streaming indicator."""
    
    status: Reactive[str] = "ready"  # "ready" | "streaming" | "error" | "disconnected"
    
    def render(self) -> str:
        icons = {
            "ready": "● Ready",
            "streaming": "◌ Streaming...",
            "error": "✗ Error",
            "disconnected": "○ Disconnected"
        }
        return icons.get(self.status, "")
```

---

## 5. State Management

### Conversation State

```python
@dataclass
class ConversationState:
    conversation_id: str | None = None
    messages: list[MessageData] = field(default_factory=list)
    pending_request_id: str | None = None
    is_streaming: bool = False
    last_error: str | None = None

@dataclass
class MessageData:
    message_id: str
    role: Literal["user", "assistant"]
    content: str
    status: Literal["final", "streaming", "error", "interrupted"]
    created_at: datetime | None = None
```

### State Updates

State is managed in `ChatApp` and propagated to widgets via Textual's reactive system:

```python
class ChatApp(App):
    state: Reactive[ConversationState]
    
    def watch_state(self, state: ConversationState) -> None:
        # Update widgets when state changes
        self.query_one(Composer).is_streaming = state.is_streaming
        self.query_one(StatusBar).status = "streaming" if state.is_streaming else "ready"
```

---

## 6. Transport Layer

### ChatClient

Handles all HTTP communication with the backend.

```python
class ChatClient:
    """HTTP client for chat backend communication."""
    
    def __init__(self, base_url: str, auth_token: str | None = None):
        self.base_url = base_url
        self.auth_token = auth_token
        self._client = httpx.AsyncClient()
        self._abort_controller: asyncio.Event | None = None
    
    async def send_message(
        self,
        content: str,
        conversation_id: str | None = None,
    ) -> AsyncIterator[StreamEvent]:
        """Send message and yield streaming events."""
        
        request_id = str(uuid.uuid4())
        self._abort_controller = asyncio.Event()
        
        headers = {"Accept": "application/x-ndjson"}
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"
        
        payload = {
            "request_id": request_id,
            "conversation_id": conversation_id,
            "message": {"role": "user", "content": content},
        }
        
        async with self._client.stream(
            "POST",
            f"{self.base_url}/v1/chat",
            json=payload,
            headers=headers,
        ) as response:
            async for line in response.aiter_lines():
                if self._abort_controller.is_set():
                    break
                if line.strip():
                    yield self._parse_event(line)
    
    def abort(self) -> None:
        """Abort current streaming request."""
        if self._abort_controller:
            self._abort_controller.set()
    
    def _parse_event(self, line: str) -> StreamEvent:
        data = json.loads(line)
        return StreamEvent(**data)
```

### Stream Events

```python
@dataclass
class StreamEvent:
    type: Literal["message.start", "message.delta", "message.done", "error"]
    conversation_id: str | None = None
    message_id: str | None = None
    delta: str | None = None
    code: str | None = None
    message: str | None = None
    metadata: dict | None = None
```

---

## 7. Event Flow

### Send Message Flow

```
User types → Enter key
    ↓
Composer emits SendMessage(text)
    ↓
ChatApp handles event:
    1. Add user message to state
    2. Create placeholder assistant message (streaming)
    3. Call transport.send_message()
    4. For each StreamEvent:
       - message.start → Store conversation_id, message_id
       - message.delta → Append to assistant message content
       - message.done → Mark message final
       - error → Mark message error, store error
    5. Update state.is_streaming = False
    ↓
Widgets react to state changes
```

### Stop Streaming Flow

```
User clicks Stop / presses Escape
    ↓
Composer emits StopStreaming()
    ↓
ChatApp handles event:
    1. Call transport.abort()
    2. Mark current message as "interrupted"
    3. Update state.is_streaming = False
```

### Retry Flow

```
User clicks Retry on error message
    ↓
ChatMessage emits RetryMessage(message_id)
    ↓
ChatApp handles event:
    1. Find original user message
    2. Remove error assistant message
    3. Re-send via transport
```

---

## 8. Styling (TCSS)

```css
/* chat.tcss */

ChatApp {
    layout: vertical;
}

MessageList {
    height: 1fr;
    border: round $primary;
    padding: 1;
}

ChatMessage {
    margin-bottom: 1;
    padding: 1;
}

ChatMessage.user {
    background: $surface;
    border-left: thick $primary;
}

ChatMessage.assistant {
    background: $surface-darken-1;
    border-left: thick $secondary;
}

ChatMessage.streaming .content {
    /* Animated cursor effect */
}

ChatMessage.error {
    border-left: thick $error;
}

Composer {
    height: auto;
    max-height: 10;
    dock: bottom;
    padding: 1;
}

Composer TextArea {
    height: auto;
    min-height: 3;
}

StatusBar {
    height: 1;
    dock: bottom;
    background: $surface;
    color: $text-muted;
}
```

---

## 9. Configuration

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `CHAT_BACKEND_URL` | Yes | — | Backend base URL |
| `CHAT_AUTH_TOKEN` | No | — | Bearer token for auth header |
| `CHAT_STREAMING` | No | `true` | Enable streaming mode |

### Config File (optional)

```toml
# config.toml
[backend]
url = "http://localhost:8000"
streaming = true

[ui]
theme = "dark"
```

---

## 10. File Structure

```
implementations/textual/
├── technical_design.md          # This document
├── pyproject.toml               # Poetry project config
├── src/
│   ├── __init__.py
│   ├── chat_app.py              # Main Textual App
│   ├── config.py                # Configuration loading
│   ├── state.py                 # ConversationState, MessageData
│   ├── widgets/
│   │   ├── __init__.py
│   │   ├── chat_message.py      # ChatMessage widget
│   │   ├── message_list.py      # MessageList container
│   │   ├── composer.py          # Composer input
│   │   └── status_bar.py        # StatusBar widget
│   ├── transport/
│   │   ├── __init__.py
│   │   ├── client.py            # ChatClient HTTP transport
│   │   └── events.py            # StreamEvent dataclasses
│   └── styles/
│       └── chat.tcss            # Textual CSS styles
└── tests/
    ├── __init__.py
    ├── test_widgets.py          # Widget unit tests
    ├── test_transport.py        # Transport unit tests
    └── test_integration.py      # End-to-end with echo server
```

---

## 11. Dependencies

```toml
[tool.poetry.dependencies]
python = "^3.13"
textual = "^3.0"
httpx = "^0.28"
python-dotenv = "^1.0"

[tool.poetry.group.dev.dependencies]
pytest = "^8.0"
pytest-asyncio = "^0.24"
textual-dev = "^1.0"
```

---

## 12. Textual Web Considerations

For future browser deployment:

1. **Same codebase** — No changes to widgets or transport
2. **Serve via textual-web:**
   ```bash
   textual-web serve src.chat_app:ChatApp
   ```
3. **Image rendering** — Plan for `textual-image` widget with web fallback
4. **Platform detection** — Use `app.is_web` to adjust behavior if needed

---

## 13. Open Questions

1. **Message editing** — Should users be able to edit sent messages?
2. **Copy button** — Where to place copy-to-clipboard action?
3. **History persistence** — localStorage equivalent for terminal?
4. **Multi-conversation** — Tabs or sidebar for conversation switching?

---

## 14. Acceptance Criteria

- [ ] App launches and displays empty chat
- [ ] User can type and send messages
- [ ] Streaming responses render incrementally
- [ ] Stop button aborts streaming
- [ ] Error states show with retry option
- [ ] Styling via TCSS variables
- [ ] Works with echo-server
- [ ] Keyboard navigation functional