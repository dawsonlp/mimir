"""Message composer widget with input and controls."""

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Button, Input


class Composer(Widget):
    """Message input with send/stop buttons."""
    
    DEFAULT_CSS = """
    Composer {
        layout: vertical;
        height: auto;
        max-height: 12;
        dock: bottom;
        padding: 1;
        background: $surface;
    }
    
    Composer Input {
        width: 100%;
    }
    
    Composer .buttons {
        height: auto;
        margin-top: 1;
        align: right middle;
    }
    
    Composer .buttons Button {
        margin-left: 1;
    }
    
    Composer #stop-btn {
        display: none;
    }
    
    Composer.streaming #stop-btn {
        display: block;
    }
    
    Composer.streaming #send-btn {
        display: none;
    }
    """
    
    is_streaming: reactive[bool] = reactive(False)
    
    class SendMessage(Message):
        """Message sent when user wants to send their input."""
        
        def __init__(self, content: str) -> None:
            self.content = content
            super().__init__()
    
    class StopStreaming(Message):
        """Message sent when user wants to stop streaming."""
        pass
    
    def compose(self) -> ComposeResult:
        """Compose the composer widget."""
        yield Input(id="input", placeholder="Type a message...")
        with Horizontal(classes="buttons"):
            yield Button("Send", id="send-btn", variant="primary")
            yield Button("Stop", id="stop-btn", variant="warning")
    
    def on_mount(self) -> None:
        """Focus the input on mount."""
        self.query_one("#input", Input).focus()
    
    def watch_is_streaming(self, streaming: bool) -> None:
        """Update CSS class when streaming state changes."""
        if streaming:
            self.add_class("streaming")
        else:
            self.remove_class("streaming")
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "send-btn":
            self._send_message()
        elif event.button.id == "stop-btn":
            self.post_message(self.StopStreaming())
    
    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle Enter key in input."""
        self._send_message()
    
    def _send_message(self) -> None:
        """Send the current input as a message."""
        input_widget = self.query_one("#input", Input)
        content = input_widget.value.strip()
        
        if content and not self.is_streaming:
            self.post_message(self.SendMessage(content))
            input_widget.value = ""
            input_widget.focus()
    
    def clear_input(self) -> None:
        """Clear the input."""
        self.query_one("#input", Input).value = ""
    
    def focus_input(self) -> None:
        """Focus the input."""
        self.query_one("#input", Input).focus()
