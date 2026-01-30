"""Main Chat Application."""

import argparse
import os
import sys
import uuid

from dotenv import load_dotenv
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Footer, Header, Static

from .transport import ChatClient
from .transcript import TranscriptLogger
from .widgets import Composer, MessageList

# Load environment variables
load_dotenv()


class StatusBar(Static):
    """Status bar showing connection state and backend info."""
    
    DEFAULT_CSS = """
    StatusBar {
        height: 1;
        dock: bottom;
        background: $surface;
        color: $text-muted;
        padding: 0 1;
    }
    """
    
    def __init__(self, backend_url: str = "", **kwargs):
        super().__init__("○ Connecting...", **kwargs)
        self.backend_url = backend_url
        self._status = "connecting"
    
    def set_status(self, status: str) -> None:
        """Set the status text."""
        self._status = status
        icons = {
            "ready": "●",
            "streaming": "◌",
            "error": "✗",
            "connecting": "○",
        }
        icon = icons.get(status, "?")
        status_text = {
            "ready": "Ready",
            "streaming": "Streaming...",
            "error": "Error",
            "connecting": "Connecting...",
        }
        text = status_text.get(status, status)
        
        # Show backend URL in status bar
        if self.backend_url:
            self.update(f"{icon} {text} │ {self.backend_url}")
        else:
            self.update(f"{icon} {text}")


class ChatApp(App):
    """Textual Chat UI - thin client for chat backends."""
    
    TITLE = "Mimir Chat"
    
    CSS = """
    Screen {
        layout: vertical;
    }
    """
    
    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit"),
        Binding("ctrl+n", "new_conversation", "New Chat"),
        Binding("escape", "stop_streaming", "Stop", show=False),
    ]
    
    def __init__(
        self,
        backend_url: str | None = None,
        auth_token: str | None = None,
        transcript_file: str | None = None,
        **kwargs,
    ):
        """Initialize the chat app.
        
        Args:
            backend_url: Backend URL (defaults to CHAT_BACKEND_URL env var)
            auth_token: Auth token (defaults to CHAT_AUTH_TOKEN env var)
            transcript_file: Optional file path for transcript logging
        """
        super().__init__(**kwargs)
        
        self.backend_url = backend_url or os.getenv(
            "CHAT_BACKEND_URL", "http://localhost:8000"
        )
        self.auth_token = auth_token or os.getenv("CHAT_AUTH_TOKEN")
        
        self.client = ChatClient(
            base_url=self.backend_url,
            auth_token=self.auth_token,
        )
        
        # Transcript logging
        self.transcript: TranscriptLogger | None = None
        if transcript_file:
            self.transcript = TranscriptLogger(transcript_file)
        
        # Conversation state
        self.conversation_id: str | None = None
        self.current_message_id: str | None = None
        self.current_assistant_content: str = ""
        self.is_streaming: bool = False
    
    def compose(self) -> ComposeResult:
        """Compose the app layout."""
        yield Header()
        yield MessageList(id="messages")
        yield Composer(id="composer")
        yield StatusBar(backend_url=self.backend_url, id="status")
        yield Footer()
    
    async def on_mount(self) -> None:
        """Initialize on mount."""
        # Open transcript file if configured
        if self.transcript:
            self.transcript.open()
            self.notify(f"Logging to {self.transcript.filepath}")
        
        # Check backend health
        status_bar = self.query_one("#status", StatusBar)
        status_bar.set_status("connecting")
        
        healthy = await self.client.health_check()
        if healthy:
            status_bar.set_status("ready")
        else:
            status_bar.set_status("error")
            self.notify(
                f"Could not connect to backend at {self.backend_url}",
                severity="error",
            )
    
    async def on_composer_send_message(self, event: Composer.SendMessage) -> None:
        """Handle send message from composer."""
        await self._send_message(event.content)
    
    async def on_composer_stop_streaming(self, event: Composer.StopStreaming) -> None:
        """Handle stop streaming request."""
        self._stop_streaming()
    
    async def _send_message(self, content: str) -> None:
        """Send a message to the backend and handle the response stream."""
        if self.is_streaming:
            return
        
        messages = self.query_one("#messages", MessageList)
        composer = self.query_one("#composer", Composer)
        status_bar = self.query_one("#status", StatusBar)
        
        # Add user message
        user_message_id = str(uuid.uuid4())[:8]
        messages.add_message(
            message_id=user_message_id,
            role="user",
            content=content,
            status="final",
        )
        
        # Log user message to transcript
        if self.transcript:
            self.transcript.log_message("user", content)
        
        # Create placeholder assistant message
        self.current_message_id = str(uuid.uuid4())[:8]
        self.current_assistant_content = ""
        messages.add_message(
            message_id=self.current_message_id,
            role="assistant",
            content="",
            status="streaming",
        )
        
        # Update UI state
        self.is_streaming = True
        composer.is_streaming = True
        status_bar.set_status("streaming")
        
        # Stream the response
        try:
            async for event in self.client.send_message(
                content=content,
                conversation_id=self.conversation_id,
            ):
                if not self.is_streaming:
                    # Aborted
                    break
                
                if event.type == "message.start":
                    # Store conversation ID for subsequent messages
                    if event.conversation_id:
                        self.conversation_id = event.conversation_id
                    # Update message ID if server provides one
                    if event.message_id and self.current_message_id:
                        # We keep our local ID for simplicity
                        pass
                
                elif event.type == "message.delta":
                    # Append content
                    if event.delta and self.current_message_id:
                        self.current_assistant_content += event.delta
                        messages.append_to_message(
                            self.current_message_id,
                            event.delta,
                        )
                
                elif event.type == "message.done":
                    # Mark as final
                    if self.current_message_id:
                        messages.set_message_status(
                            self.current_message_id,
                            "final",
                        )
                        # Log assistant message to transcript
                        if self.transcript and self.current_assistant_content:
                            self.transcript.log_message(
                                "assistant",
                                self.current_assistant_content,
                            )
                
                elif event.type == "error":
                    # Mark as error
                    if self.current_message_id:
                        error_text = event.message or "Unknown error"
                        messages.update_message_content(
                            self.current_message_id,
                            f"Error: {error_text}",
                        )
                        messages.set_message_status(
                            self.current_message_id,
                            "error",
                        )
                    self.notify(
                        event.message or "An error occurred",
                        severity="error",
                    )
        
        except Exception as e:
            # Handle unexpected errors
            if self.current_message_id:
                messages.update_message_content(
                    self.current_message_id,
                    f"Error: {e}",
                )
                messages.set_message_status(self.current_message_id, "error")
            self.notify(str(e), severity="error")
        
        finally:
            # Reset state
            self.is_streaming = False
            self.current_message_id = None
            composer.is_streaming = False
            status_bar.set_status("ready")
            composer.focus_input()
    
    def _stop_streaming(self) -> None:
        """Stop the current streaming request."""
        if self.is_streaming:
            self.client.abort()
            self.is_streaming = False
            
            # Mark current message as interrupted
            if self.current_message_id:
                messages = self.query_one("#messages", MessageList)
                messages.set_message_status(self.current_message_id, "final")
            
            # Reset UI
            composer = self.query_one("#composer", Composer)
            status_bar = self.query_one("#status", StatusBar)
            composer.is_streaming = False
            status_bar.set_status("ready")
    
    def action_stop_streaming(self) -> None:
        """Action to stop streaming (bound to Escape)."""
        self._stop_streaming()
    
    def action_new_conversation(self) -> None:
        """Start a new conversation."""
        self._stop_streaming()
        self.conversation_id = None
        messages = self.query_one("#messages", MessageList)
        messages.clear_messages()
        self.notify("Started new conversation")
    
    async def on_unmount(self) -> None:
        """Clean up on unmount."""
        await self.client.close()
        if self.transcript:
            self.transcript.close()


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Mimir Chat UI - Terminal chat client",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                          # Run without transcript logging
  %(prog)s chat.md                  # Log to Markdown file
  %(prog)s session.json             # Log to NDJSON file
  
Transcript formats (detected by extension):
  .md, .markdown    Markdown format (human-readable)
  .json, .jsonl     NDJSON format (machine-readable)
        """,
    )
    parser.add_argument(
        "transcript",
        nargs="?",
        help="Optional transcript file (format detected from extension)",
    )
    parser.add_argument(
        "--backend-url",
        default=None,
        help="Backend URL (default: CHAT_BACKEND_URL env or http://localhost:8000)",
    )
    return parser.parse_args()


def main():
    """Run the chat app."""
    args = parse_args()
    app = ChatApp(
        backend_url=args.backend_url,
        transcript_file=args.transcript,
    )
    app.run()


if __name__ == "__main__":
    main()