"""Message list container widget."""

from textual.containers import VerticalScroll

from .chat_message import ChatMessage


class MessageList(VerticalScroll):
    """Scrollable container for chat messages with auto-scroll."""
    
    DEFAULT_CSS = """
    MessageList {
        height: 1fr;
        border: round $primary;
        padding: 1;
    }
    """
    
    def add_message(
        self,
        message_id: str,
        role: str,
        content: str = "",
        status: str = "final",
    ) -> ChatMessage:
        """Add a new message to the list.
        
        Args:
            message_id: Unique identifier for the message
            role: "user" or "assistant"
            content: Message content text
            status: "final", "streaming", or "error"
            
        Returns:
            The created ChatMessage widget
        """
        message = ChatMessage(
            message_id=message_id,
            role=role,
            content=content,
            status=status,
        )
        self.mount(message)
        self.scroll_end(animate=False)
        return message
    
    def get_message(self, message_id: str) -> ChatMessage | None:
        """Get a message by ID.
        
        Args:
            message_id: The message identifier
            
        Returns:
            The ChatMessage widget or None if not found
        """
        try:
            return self.query_one(f"#msg-{message_id}", ChatMessage)
        except Exception:
            return None
    
    def update_message_content(self, message_id: str, content: str) -> None:
        """Update a message's content.
        
        Args:
            message_id: The message identifier
            content: New content to set
        """
        message = self.get_message(message_id)
        if message:
            message.content = content
            self.scroll_end(animate=False)
    
    def append_to_message(self, message_id: str, delta: str) -> None:
        """Append content to a message (for streaming).
        
        Args:
            message_id: The message identifier
            delta: Content to append
        """
        message = self.get_message(message_id)
        if message:
            message.append_content(delta)
            self.scroll_end(animate=False)
    
    def set_message_status(self, message_id: str, status: str) -> None:
        """Set a message's status.
        
        Args:
            message_id: The message identifier
            status: "final", "streaming", or "error"
        """
        message = self.get_message(message_id)
        if message:
            message.status = status
    
    def clear_messages(self) -> None:
        """Remove all messages from the list."""
        for message in self.query(ChatMessage):
            message.remove()