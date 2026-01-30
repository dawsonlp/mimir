"""HTTP client for chat backend communication."""

import asyncio
import json
import uuid
from collections.abc import AsyncIterator

import httpx

from .events import StreamEvent


class ChatClient:
    """HTTP client for chat backend communication.
    
    Handles streaming NDJSON responses from the backend.
    """
    
    def __init__(
        self,
        base_url: str,
        auth_token: str | None = None,
        timeout: float = 60.0,
    ):
        """Initialize the chat client.
        
        Args:
            base_url: Backend base URL (e.g., "http://localhost:8000")
            auth_token: Optional bearer token for authentication
            timeout: Request timeout in seconds
        """
        self.base_url = base_url.rstrip("/")
        self.auth_token = auth_token
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None
        self._abort_event: asyncio.Event | None = None
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client
    
    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None
    
    async def send_message(
        self,
        content: str,
        conversation_id: str | None = None,
    ) -> AsyncIterator[StreamEvent]:
        """Send a message and yield streaming events.
        
        Args:
            content: The message content to send
            conversation_id: Optional conversation ID (omit to start new conversation)
            
        Yields:
            StreamEvent objects as they arrive from the backend
        """
        request_id = str(uuid.uuid4())
        self._abort_event = asyncio.Event()
        
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/x-ndjson",
        }
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"
        
        payload = {
            "request_id": request_id,
            "message": {"role": "user", "content": content},
        }
        if conversation_id:
            payload["conversation_id"] = conversation_id
        
        client = await self._get_client()
        
        try:
            async with client.stream(
                "POST",
                f"{self.base_url}/v1/chat",
                json=payload,
                headers=headers,
            ) as response:
                response.raise_for_status()
                
                async for line in response.aiter_lines():
                    # Check for abort
                    if self._abort_event and self._abort_event.is_set():
                        break
                    
                    # Parse NDJSON line
                    line = line.strip()
                    if line:
                        try:
                            data = json.loads(line)
                            yield StreamEvent.from_dict(data)
                        except json.JSONDecodeError:
                            # Skip malformed lines
                            continue
                            
        except httpx.HTTPStatusError as e:
            # Convert HTTP errors to error events
            yield StreamEvent(
                type="error",
                code=f"http_{e.response.status_code}",
                message=f"HTTP {e.response.status_code}: {e.response.text}",
            )
        except httpx.RequestError as e:
            # Convert network errors to error events
            yield StreamEvent(
                type="error",
                code="network_error",
                message=str(e),
            )
    
    def abort(self) -> None:
        """Abort the current streaming request."""
        if self._abort_event:
            self._abort_event.set()
    
    async def health_check(self) -> bool:
        """Check if the backend is healthy.
        
        Returns:
            True if healthy, False otherwise
        """
        try:
            client = await self._get_client()
            response = await client.get(f"{self.base_url}/health")
            return response.status_code == 200
        except httpx.RequestError:
            return False