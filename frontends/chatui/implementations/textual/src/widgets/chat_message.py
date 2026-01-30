"""Chat message widget."""

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static, Markdown, Button


class ChatMessage(Widget):
    """A single chat message with role and content."""
    
    DEFAULT_CSS = """
    ChatMessage {
        layout: vertical;
        height: auto;
        margin-bottom: 1;
        padding: 0 1;
    }
    
    ChatMessage.user {
        background: $surface;
        border-left: thick $primary;
    }
    
    ChatMessage.assistant {
        background: $surface-darken-1;
        border-left: thick $secondary;
    }
    
    ChatMessage.streaming {
        border-left: thick $warning;
    }
    
    ChatMessage.error {
        border-left: thick $error;
    }
    
    ChatMessage .role-label {
        color: $text-muted;
        text-style: bold;
        height: auto;
    }
    
    ChatMessage .content {
        height: auto;
        margin: 0;
        padding: 0;
    }
    
    ChatMessage Markdown {
        height: auto;
        margin: 0;
        padding: 0;
    }
    
    ChatMessage .message-header {
        height: auto;
    }
    
    ChatMessage .copy-btn {
        min-width: 6;
        height: 1;
        margin: 0;
        padding: 0 1;
        dock: right;
    }
    """
    
    role: reactive[str] = reactive("user")
    content: reactive[str] = reactive("")
    status: reactive[str] = reactive("final")  # "final" | "streaming" | "error"
    
    def __init__(
        self,
        message_id: str,
        role: str,
        content: str = "",
        status: str = "final",
        **kwargs,
    ):
        """Initialize a chat message.
        
        Args:
            message_id: Unique identifier for this message
            role: "user" or "assistant"
            content: Message content text
            status: "final", "streaming", or "error"
        """
        super().__init__(id=f"msg-{message_id}", **kwargs)
        self.message_id = message_id
        self.role = role
        self.content = content
        self.status = status
    
    def on_mount(self) -> None:
        """Apply initial CSS classes on mount."""
        self.add_class(self.role)
        self.add_class(self.status)
    
    def compose(self) -> ComposeResult:
        """Compose the message widget."""
        role_label = "You" if self.role == "user" else "Assistant"
        with Horizontal(classes="message-header"):
            yield Static(role_label, classes="role-label")
            yield Button("Copy", id="copy-btn", classes="copy-btn", variant="default")
        yield Markdown(self.content, classes="content")
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle copy button press."""
        if event.button.id == "copy-btn":
            self.app.copy_to_clipboard(self.content)
            self.app.notify("Copied to clipboard!")
    
    def watch_role(self, role: str) -> None:
        """Update CSS classes when role changes."""
        self.remove_class("user", "assistant")
        self.add_class(role)
    
    def watch_status(self, status: str) -> None:
        """Update CSS classes when status changes."""
        self.remove_class("final", "streaming", "error")
        self.add_class(status)
    
    def watch_content(self, content: str) -> None:
        """Update the markdown content when it changes."""
        try:
            markdown = self.query_one(".content", Markdown)
            markdown.update(content)
        except Exception:
            # Widget not yet composed
            pass
    
    def append_content(self, delta: str) -> None:
        """Append content (for streaming updates)."""
        self.content = self.content + delta