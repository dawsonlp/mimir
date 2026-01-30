"""Mimir client for conversation persistence."""

import os
from datetime import datetime, timezone

import httpx


class MimirClient:
    """Client for Mimir knowledge store API.
    
    Handles conversation and message artifact persistence.
    Mimir uses integer IDs for artifacts.
    """
    
    def __init__(
        self,
        base_url: str | None = None,
        tenant_id: str | None = None,
    ):
        self.base_url = base_url or os.getenv("MIMIR_BASE_URL", "http://localhost:38000")
        self.tenant_id = tenant_id or os.getenv("MIMIR_TENANT_ID", "default")
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={"X-Tenant-ID": self.tenant_id},
            timeout=30.0,
        )
    
    async def close(self):
        """Close the HTTP client."""
        await self._client.aclose()
    
    async def health_check(self) -> bool:
        """Check if Mimir is available."""
        try:
            response = await self._client.get("/health")
            return response.status_code == 200
        except Exception:
            return False
    
    async def create_conversation(self, title: str | None = None) -> int:
        """Create a new conversation artifact.
        
        Args:
            title: Optional title for the conversation
            
        Returns:
            The conversation artifact ID (integer)
        """
        artifact_data = {
            "artifact_type": "conversation",
            "title": title or f"Conversation {datetime.now(timezone.utc).isoformat()}",
            "content": "",
            "metadata": {
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        }
        
        response = await self._client.post("/artifacts", json=artifact_data)
        response.raise_for_status()
        
        result = response.json()
        return result["id"]  # Mimir returns 'id' as integer
    
    async def add_message(
        self,
        conversation_id: int,
        role: str,
        content: str,
    ) -> int:
        """Add a message to a conversation.
        
        Args:
            conversation_id: Parent conversation artifact ID (integer)
            role: Message role ('user' or 'assistant')
            content: Message content
            
        Returns:
            The message artifact ID (integer)
        """
        artifact_data = {
            "artifact_type": "message",
            "title": f"{role} message",
            "content": content,
            "parent_artifact_id": conversation_id,  # Must be integer
            "metadata": {
                "role": role,
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        }
        
        response = await self._client.post("/artifacts", json=artifact_data)
        response.raise_for_status()
        
        result = response.json()
        return result["id"]
    
    async def get_conversation_messages(
        self,
        conversation_id: int,
    ) -> list[dict]:
        """Get all messages in a conversation.
        
        Args:
            conversation_id: The conversation artifact ID (integer)
            
        Returns:
            List of message dicts with 'role' and 'content' keys
        """
        response = await self._client.get(
            f"/artifacts/{conversation_id}/children",
            params={"artifact_type": "message"},
        )
        response.raise_for_status()
        
        children = response.json()
        
        # Sort by created_at and extract role/content
        messages = []
        for child in sorted(children, key=lambda x: x.get("created_at", "")):
            metadata = child.get("metadata", {}) or {}
            messages.append({
                "role": metadata.get("role", "user"),
                "content": child.get("content", ""),
            })
        
        return messages
    
    async def conversation_exists(self, conversation_id: int) -> bool:
        """Check if a conversation exists.
        
        Args:
            conversation_id: The conversation artifact ID (integer)
            
        Returns:
            True if the conversation exists
        """
        try:
            response = await self._client.get(f"/artifacts/{conversation_id}")
            return response.status_code == 200
        except Exception:
            return False


# Singleton instance (created on demand)
_mimir_client: MimirClient | None = None


def get_mimir_client() -> MimirClient:
    """Get the Mimir client singleton."""
    global _mimir_client
    if _mimir_client is None:
        _mimir_client = MimirClient()
    return _mimir_client