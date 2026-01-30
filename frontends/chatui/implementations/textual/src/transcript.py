"""Transcript logging for chat conversations."""

import json
from datetime import datetime, timezone
from pathlib import Path


class TranscriptLogger:
    """Logs chat messages to a file with format detection based on extension.
    
    Supported formats:
    - Markdown (.md, .markdown): Human-readable format
    - NDJSON (.json, .jsonl, .ndjson): Machine-readable format
    """
    
    MARKDOWN_EXTENSIONS = {".md", ".markdown"}
    NDJSON_EXTENSIONS = {".json", ".jsonl", ".ndjson"}
    
    def __init__(self, filepath: str | Path):
        """Initialize the transcript logger.
        
        Args:
            filepath: Path to the transcript file. Format is detected from extension.
        """
        self.filepath = Path(filepath)
        self.format = self._detect_format()
        self._file = None
    
    def _detect_format(self) -> str:
        """Detect output format from file extension."""
        ext = self.filepath.suffix.lower()
        if ext in self.NDJSON_EXTENSIONS:
            return "ndjson"
        return "markdown"  # Default to markdown
    
    def open(self) -> None:
        """Open the transcript file for appending."""
        self._file = open(self.filepath, "a", encoding="utf-8")
    
    def close(self) -> None:
        """Close the transcript file."""
        if self._file:
            self._file.close()
            self._file = None
    
    def log_message(self, role: str, content: str) -> None:
        """Log a message to the transcript.
        
        Args:
            role: Message role ("user" or "assistant")
            content: Message content
        """
        if not self._file:
            return
        
        if self.format == "ndjson":
            self._log_ndjson(role, content)
        else:
            self._log_markdown(role, content)
        
        # Flush immediately so content is available
        self._file.flush()
    
    def _log_markdown(self, role: str, content: str) -> None:
        """Log in markdown format."""
        role_label = "You" if role == "user" else "Assistant"
        self._file.write(f"### {role_label}\n")
        self._file.write(f"{content}\n\n")
    
    def _log_ndjson(self, role: str, content: str) -> None:
        """Log in NDJSON format."""
        record = {
            "role": role,
            "content": content,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._file.write(json.dumps(record) + "\n")
    
    def __enter__(self):
        """Context manager entry."""
        self.open()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
        return False