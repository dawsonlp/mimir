"""Stream event types from the chat backend."""

from dataclasses import dataclass


@dataclass
class StreamEvent:
    """A streaming event from the chat backend.
    
    Event types:
    - message.start: Stream begins, provides conversation_id and message_id
    - message.delta: Incremental content chunk
    - message.done: Stream complete
    - error: Error occurred during streaming
    """
    
    type: str  # "message.start" | "message.delta" | "message.done" | "error"
    conversation_id: str | None = None
    message_id: str | None = None
    delta: str | None = None
    code: str | None = None
    message: str | None = None
    metadata: dict | None = None
    
    @classmethod
    def from_dict(cls, data: dict) -> "StreamEvent":
        """Create a StreamEvent from a dictionary."""
        return cls(
            type=data.get("type", ""),
            conversation_id=data.get("conversation_id"),
            message_id=data.get("message_id"),
            delta=data.get("delta"),
            code=data.get("code"),
            message=data.get("message"),
            metadata=data.get("metadata"),
        )