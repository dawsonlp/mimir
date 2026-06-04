"""Legacy async httpx client for validation-scenarios.

This module predates the current v5.5 contract. The validation tool should move
to the published mimir-client package during modernization.
"""

import os
from uuid import UUID

import httpx


class MimirClient:
    """Legacy async HTTP client for older Mimir API usage.
    
    Covers artifacts, relations, context, and search endpoints.
    Uses httpx for async HTTP requests.
    """
    
    def __init__(
        self,
        base_url: str | None = None,
        tenant_id: int | None = None,
        timeout: float = 30.0,
    ):
        self.base_url = base_url or os.getenv("MIMIR_BASE_URL", "http://localhost:38000")
        self.tenant_id = tenant_id or int(os.getenv("MIMIR_TENANT_ID", "1"))
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={"X-Tenant-ID": str(self.tenant_id)},
            timeout=timeout,
        )
    
    async def close(self):
        """Close the HTTP client."""
        await self._client.aclose()
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
    
    # =========================================================================
    # Health
    # =========================================================================
    
    async def health_check(self) -> bool:
        """Check if Mímir API is available."""
        try:
            response = await self._client.get("/health")
            return response.status_code == 200
        except Exception:
            return False
    
    # =========================================================================
    # Artifacts
    # =========================================================================
    
    async def create_artifact(
        self,
        artifact_type: str,
        title: str | None = None,
        content: str | None = None,
        parent_artifact_id: UUID | None = None,
        source: str | None = None,
        source_system: str | None = None,
        external_id: str | None = None,
        metadata: dict | None = None,
    ) -> dict:
        """Create a new artifact.
        
        Returns the created artifact dict with id, created_at, etc.
        """
        data = {
            "artifact_type": artifact_type,
            "title": title,
            "content": content,
            "metadata": metadata,
        }
        if parent_artifact_id:
            data["parent_artifact_id"] = str(parent_artifact_id)
        if source:
            data["source"] = source
        if source_system:
            data["source_system"] = source_system
        if external_id:
            data["external_id"] = external_id
        
        response = await self._client.post("/artifacts", json=data)
        response.raise_for_status()
        return response.json()
    
    async def get_artifact(self, artifact_id: UUID) -> dict | None:
        """Get artifact by UUID. Returns None if not found."""
        response = await self._client.get(f"/artifacts/{artifact_id}")
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()
    
    async def list_artifacts(
        self,
        artifact_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict:
        """List artifacts with pagination and optional type filter."""
        params = {"limit": limit, "offset": offset}
        if artifact_type:
            params["artifact_type"] = artifact_type
        
        response = await self._client.get("/artifacts", params=params)
        response.raise_for_status()
        return response.json()
    
    async def batch_get_artifacts(self, ids: list[UUID]) -> list[dict]:
        """Batch retrieve artifacts by UUIDs. Missing IDs silently omitted."""
        if not ids:
            return []
        
        ids_param = ",".join(str(id) for id in ids)
        response = await self._client.get("/artifacts", params={"ids": ids_param})
        response.raise_for_status()
        return response.json().get("items", [])
    
    async def get_artifact_children(self, artifact_id: UUID) -> list[dict]:
        """Get child artifacts (for positional types)."""
        response = await self._client.get(f"/artifacts/{artifact_id}/children")
        response.raise_for_status()
        return response.json()
    
    # =========================================================================
    # Relations
    # =========================================================================
    
    async def create_relation(
        self,
        source_id: UUID,
        target_id: UUID,
        relation_type: str,
        confidence: float = 1.0,
        metadata: dict | None = None,
    ) -> dict:
        """Create a relation between two artifacts."""
        data = {
            "source_id": str(source_id),
            "target_id": str(target_id),
            "relation_type": relation_type,
            "confidence": confidence,
            "metadata": metadata,
        }
        response = await self._client.post("/relations", json=data)
        response.raise_for_status()
        return response.json()
    
    async def get_artifact_relations(
        self,
        artifact_id: UUID,
        as_source: bool = True,
        as_target: bool = True,
        relation_type: str | None = None,
    ) -> list[dict]:
        """Get relations for an artifact."""
        params = {
            "as_source": as_source,
            "as_target": as_target,
        }
        if relation_type:
            params["relation_type"] = relation_type
        
        response = await self._client.get(
            f"/relations/artifact/{artifact_id}", params=params
        )
        response.raise_for_status()
        return response.json()
    
    # =========================================================================
    # Context (RAG context retrieval)
    # =========================================================================
    
    async def get_context(
        self,
        artifact_id: UUID,
        policy: str = "derived_lineage",
        depth: int = 2,
        types: list[str] | None = None,
        include_content: bool = True,
    ) -> dict | None:
        """Get artifact with assembled context for RAG.
        
        Policies: direct_relations, derived_lineage, evidence_chain, full_graph
        """
        params = {
            "policy": policy,
            "depth": depth,
            "include_content": include_content,
        }
        if types:
            params["types"] = ",".join(types)
        
        response = await self._client.post(
            f"/context/{artifact_id}", params=params
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()
    
    # =========================================================================
    # Search
    # =========================================================================
    
    async def fulltext_search(
        self,
        query: str,
        artifact_types: list[str] | None = None,
        limit: int = 20,
        related_to: UUID | None = None,
        relation_type: str | None = None,
    ) -> dict:
        """Full-text search using PostgreSQL FTS."""
        params = {"query": query, "limit": limit}
        if artifact_types:
            params["artifact_types"] = artifact_types
        if related_to:
            params["related_to"] = str(related_to)
        if relation_type:
            params["relation_type"] = relation_type
        
        response = await self._client.get("/search/fulltext", params=params)
        response.raise_for_status()
        return response.json()


def get_client() -> MimirClient:
    """Factory function to create MimirClient from environment."""
    return MimirClient()
