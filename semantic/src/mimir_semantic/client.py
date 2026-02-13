"""Mímir Storage API Client.

Provides typed Python methods for all Mímir Storage API endpoints.
Each method documents the underlying API endpoint with links to documentation.
"""

from typing import Any
from uuid import UUID

import httpx

from mimir_semantic.config import Settings, get_settings
from mimir_semantic.exceptions import (
    MimirAPIError,
    MimirConnectionError,
    MimirNotFoundError,
    MimirTenantError,
    MimirValidationError,
)


class MimirClient:
    """Client for Mímir Storage API.
    
    All storage operations go through this client. It provides:
    - Typed Python methods for all API endpoints
    - Automatic tenant ID header injection
    - Documentation links in every method docstring
    - Connection pooling via httpx
    
    Parameters
    ----------
    base_url : str
        Base URL for the Mímir Storage API (default: http://localhost:38000)
    docs_url : str, optional
        Base URL for API documentation (default: {base_url}/docs)
    tenant_id : int, optional
        Default tenant ID for tenant-scoped operations
    timeout : float
        HTTP request timeout in seconds (default: 30.0)
    
    Example
    -------
    >>> client = MimirClient(
    ...     base_url="http://localhost:38000",
    ...     tenant_id=1,
    ... )
    >>> artifact = await client.get_artifact("abc123-...")
    >>> await client.close()
    
    See Also
    --------
    MimirClient.from_env : Create client from environment variables
    """
    
    def __init__(
        self,
        base_url: str = "http://localhost:38000",
        docs_url: str | None = None,
        tenant_id: int | None = None,
        timeout: float = 30.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.docs_url = (docs_url or f"{self.base_url}/docs").rstrip("/")
        self.tenant_id = tenant_id
        self._http = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=timeout,
        )
    
    @classmethod
    def from_env(cls) -> "MimirClient":
        """Create client from environment variables.
        
        Reads configuration from environment variables and .env files.
        
        Environment Variables
        ---------------------
        MIMIR_API_URL : str
            Base URL for API calls (default: http://localhost:38000)
        MIMIR_DOCS_URL : str, optional
            Base URL for documentation links (default: {MIMIR_API_URL}/docs)
        MIMIR_TENANT_ID : int, optional
            Default tenant ID for operations
        
        Returns
        -------
        MimirClient
            Configured client instance
        
        Example
        -------
        >>> # Set environment variables or use .env file
        >>> client = MimirClient.from_env()
        """
        settings = get_settings()
        return cls(
            base_url=settings.api_url,
            docs_url=settings.resolved_docs_url,
            tenant_id=settings.tenant_id,
        )
    
    def _doc_link(self, anchor: str) -> str:
        """Generate documentation link for an endpoint."""
        return f"{self.docs_url}#{anchor}"
    
    def _headers(self, require_tenant: bool = False) -> dict[str, str]:
        """Build request headers with optional tenant ID."""
        headers = {"Content-Type": "application/json"}
        if self.tenant_id is not None:
            headers["X-Tenant-ID"] = str(self.tenant_id)
        elif require_tenant:
            raise MimirTenantError()
        return headers
    
    async def _handle_response(self, response: httpx.Response, endpoint: str) -> Any:
        """Handle API response, raising appropriate exceptions."""
        if response.status_code == 404:
            detail = response.json().get("detail", "Not found")
            raise MimirNotFoundError("Resource", "unknown", endpoint)
        
        if response.status_code == 422:
            data = response.json()
            errors = data.get("detail", [])
            if isinstance(errors, str):
                errors = [{"msg": errors}]
            raise MimirValidationError(errors, endpoint)
        
        if response.status_code >= 400:
            detail = response.text
            try:
                detail = response.json().get("detail", detail)
            except Exception:
                pass
            raise MimirAPIError(response.status_code, str(detail), endpoint)
        
        return response.json()
    
    async def close(self) -> None:
        """Close the HTTP client connection pool.
        
        Should be called when done using the client.
        
        Example
        -------
        >>> client = MimirClient.from_env()
        >>> try:
        ...     artifact = await client.get_artifact("...")
        ... finally:
        ...     await client.close()
        """
        await self._http.aclose()
    
    async def __aenter__(self) -> "MimirClient":
        """Async context manager entry."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.close()
    
    # =========================================================================
    # Health
    # =========================================================================
    
    async def health(self) -> dict:
        """Check API health status.
        
        API Reference
        -------------
        GET /health
        
        See: {docs_url}#/default/health_health_get
        
        Returns
        -------
        dict
            Health status with keys: status, version
        
        Example
        -------
        >>> health = await client.health()
        >>> print(health["status"])
        healthy
        """
        try:
            response = await self._http.get("/health")
            return await self._handle_response(response, "/health")
        except httpx.ConnectError as e:
            raise MimirConnectionError(str(e), self.base_url)
    
    # =========================================================================
    # Tenants
    # =========================================================================
    
    async def create_tenant(
        self,
        shortname: str,
        name: str,
        tenant_type: str = "experiment",
        description: str | None = None,
        metadata: dict | None = None,
    ) -> dict:
        """Create a new tenant.
        
        API Reference
        -------------
        POST /tenants
        
        See: {docs_url}#/Tenants/create_tenant_tenants_post
        
        Request Body (TenantCreate):
            shortname: str - Unique short identifier
            name: str - Human-readable name
            tenant_type: str - Type: "experiment", "project", "team"
            description: str | None - Optional description
            metadata: dict | None - Optional JSON metadata
        
        Response (TenantResponse):
            id: int - Server-assigned ID
            shortname: str
            name: str
            tenant_type: str
            is_active: bool
            created_at: datetime
        
        Parameters
        ----------
        shortname : str
            Unique short identifier for the tenant
        name : str
            Human-readable name
        tenant_type : str
            Type of tenant (default: "experiment")
        description : str, optional
            Optional description
        metadata : dict, optional
            Optional JSON metadata
        
        Returns
        -------
        dict
            Created tenant data
        
        Example
        -------
        >>> tenant = await client.create_tenant(
        ...     shortname="my-project",
        ...     name="My Project",
        ... )
        >>> print(tenant["id"])
        1
        """
        response = await self._http.post(
            "/tenants",
            headers={"Content-Type": "application/json"},
            json={
                "shortname": shortname,
                "name": name,
                "tenant_type": tenant_type,
                "description": description,
                "metadata": metadata,
            },
        )
        return await self._handle_response(response, "/tenants")
    
    async def list_tenants(self, limit: int = 50, offset: int = 0) -> dict:
        """List all tenants.
        
        API Reference
        -------------
        GET /tenants
        
        See: {docs_url}#/Tenants/list_tenants_tenants_get
        
        Query Parameters:
            limit: int - Maximum results (default: 50)
            offset: int - Pagination offset (default: 0)
        
        Response:
            items: list[TenantResponse]
            total: int
        
        Parameters
        ----------
        limit : int
            Maximum number of results (default: 50)
        offset : int
            Pagination offset (default: 0)
        
        Returns
        -------
        dict
            List response with items and total count
        """
        response = await self._http.get(
            "/tenants",
            params={"limit": limit, "offset": offset},
        )
        return await self._handle_response(response, "/tenants")
    
    # =========================================================================
    # Artifacts
    # =========================================================================
    
    async def create_artifact(
        self,
        artifact_type: str,
        title: str,
        content: str | None = None,
        metadata: dict | None = None,
        parent_artifact_id: str | UUID | None = None,
        source: str | None = None,
        source_system: str | None = None,
        external_id: str | None = None,
    ) -> dict:
        """Create a new artifact.
        
        API Reference
        -------------
        POST /artifacts
        
        See: {docs_url}#/Artifacts/create_artifact_artifacts_post
        
        Request Headers:
            X-Tenant-ID: int (required)
        
        Request Body (ArtifactCreate):
            artifact_type: str - Type code (e.g., "document", "conversation")
            title: str - Human-readable title
            content: str | None - Full text content
            metadata: dict | None - Arbitrary JSON metadata
            parent_artifact_id: UUID | None - Parent for hierarchical types
            source: str | None - Source URL or identifier
            source_system: str | None - Source system name
            external_id: str | None - External system ID
        
        Response (ArtifactResponse):
            id: UUID - Server-assigned identifier
            tenant_id: int - Owning tenant
            content_hash: str - SHA-256 of content
            created_at: datetime - Creation timestamp
        
        Parameters
        ----------
        artifact_type : str
            Type code from artifact_type vocabulary
        title : str
            Human-readable title for the artifact
        content : str, optional
            Full text content of the artifact
        metadata : dict, optional
            Additional properties as JSON
        parent_artifact_id : str or UUID, optional
            Parent artifact for hierarchical types
        source : str, optional
            Source URL or identifier
        source_system : str, optional
            Source system name
        external_id : str, optional
            External system ID
        
        Returns
        -------
        dict
            Created artifact data
        
        Raises
        ------
        MimirTenantError
            If tenant_id not configured
        MimirValidationError
            If artifact_type is not in vocabulary
        
        Example
        -------
        >>> artifact = await client.create_artifact(
        ...     artifact_type="document",
        ...     title="Meeting Notes",
        ...     content="Discussion about Q1 goals...",
        ... )
        >>> print(artifact["id"])
        abc123-...
        """
        response = await self._http.post(
            "/artifacts",
            headers=self._headers(require_tenant=True),
            json={
                "artifact_type": artifact_type,
                "title": title,
                "content": content,
                "metadata": metadata or {},
                "parent_artifact_id": str(parent_artifact_id) if parent_artifact_id else None,
                "source": source,
                "source_system": source_system,
                "external_id": external_id,
            },
        )
        return await self._handle_response(response, "/artifacts")
    
    async def get_artifact(self, artifact_id: str | UUID) -> dict:
        """Get an artifact by ID.
        
        API Reference
        -------------
        GET /artifacts/{artifact_id}
        
        See: {docs_url}#/Artifacts/get_artifact_artifacts__artifact_id__get
        
        Request Headers:
            X-Tenant-ID: int (required)
        
        Path Parameters:
            artifact_id: UUID
        
        Response (ArtifactResponse):
            Full artifact data including content
        
        Parameters
        ----------
        artifact_id : str or UUID
            Artifact identifier
        
        Returns
        -------
        dict
            Artifact data
        
        Raises
        ------
        MimirNotFoundError
            If artifact does not exist
        """
        endpoint = f"/artifacts/{artifact_id}"
        response = await self._http.get(
            endpoint,
            headers=self._headers(require_tenant=True),
        )
        return await self._handle_response(response, endpoint)
    
    async def list_artifacts(
        self,
        artifact_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict:
        """List artifacts for the current tenant.
        
        API Reference
        -------------
        GET /artifacts
        
        See: {docs_url}#/Artifacts/list_artifacts_artifacts_get
        
        Request Headers:
            X-Tenant-ID: int (required)
        
        Query Parameters:
            artifact_type: str | None - Filter by type
            limit: int - Maximum results (default: 50)
            offset: int - Pagination offset (default: 0)
        
        Response:
            items: list[ArtifactResponse]
            total: int
            limit: int
            offset: int
        
        Parameters
        ----------
        artifact_type : str, optional
            Filter by artifact type
        limit : int
            Maximum number of results (default: 50)
        offset : int
            Pagination offset (default: 0)
        
        Returns
        -------
        dict
            List response with items and total count
        """
        params = {"limit": limit, "offset": offset}
        if artifact_type:
            params["artifact_type"] = artifact_type
        
        response = await self._http.get(
            "/artifacts",
            headers=self._headers(require_tenant=True),
            params=params,
        )
        return await self._handle_response(response, "/artifacts")
    
    # =========================================================================
    # Relations
    # =========================================================================
    
    async def create_relation(
        self,
        source_id: str | UUID,
        target_id: str | UUID,
        relation_type: str,
        confidence: float = 1.0,
        metadata: dict | None = None,
    ) -> dict:
        """Create a relation between two artifacts.
        
        API Reference
        -------------
        POST /relations
        
        See: {docs_url}#/Relations/create_relation_relations_post
        
        Request Headers:
            X-Tenant-ID: int (required)
        
        Request Body (RelationCreate):
            source_id: UUID - Source artifact
            target_id: UUID - Target artifact
            relation_type: str - Type code (e.g., "derived_from", "references")
            confidence: float - Confidence score 0.0-1.0 (default: 1.0)
            metadata: dict | None - Optional metadata
        
        Response (RelationResponse):
            id: UUID - Relation identifier
            source_id, target_id, relation_type, confidence
            created_at: datetime
        
        Parameters
        ----------
        source_id : str or UUID
            Source artifact ID
        target_id : str or UUID
            Target artifact ID
        relation_type : str
            Relation type code
        confidence : float
            Confidence score (default: 1.0)
        metadata : dict, optional
            Additional metadata
        
        Returns
        -------
        dict
            Created relation data
        
        Example
        -------
        >>> relation = await client.create_relation(
        ...     source_id=analysis_id,
        ...     target_id=document_id,
        ...     relation_type="derived_from",
        ... )
        """
        response = await self._http.post(
            "/relations",
            headers=self._headers(require_tenant=True),
            json={
                "source_id": str(source_id),
                "target_id": str(target_id),
                "relation_type": relation_type,
                "confidence": confidence,
                "metadata": metadata,
            },
        )
        return await self._handle_response(response, "/relations")
    
    async def list_relations(
        self,
        source_id: str | UUID | None = None,
        target_id: str | UUID | None = None,
        relation_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict:
        """List relations with optional filters.
        
        API Reference
        -------------
        GET /relations
        
        See: {docs_url}#/Relations/list_relations_relations_get
        
        Request Headers:
            X-Tenant-ID: int (required)
        
        Query Parameters:
            source_id: UUID | None - Filter by source
            target_id: UUID | None - Filter by target
            relation_type: str | None - Filter by type
            limit: int - Maximum results
            offset: int - Pagination offset
        
        Parameters
        ----------
        source_id : str or UUID, optional
            Filter by source artifact
        target_id : str or UUID, optional
            Filter by target artifact
        relation_type : str, optional
            Filter by relation type
        limit : int
            Maximum results (default: 50)
        offset : int
            Pagination offset (default: 0)
        
        Returns
        -------
        dict
            List response with items and total count
        """
        params = {"limit": limit, "offset": offset}
        if source_id:
            params["source_id"] = str(source_id)
        if target_id:
            params["target_id"] = str(target_id)
        if relation_type:
            params["relation_type"] = relation_type
        
        response = await self._http.get(
            "/relations",
            headers=self._headers(require_tenant=True),
            params=params,
        )
        return await self._handle_response(response, "/relations")
    
    # =========================================================================
    # Embeddings
    # =========================================================================
    
    async def create_embedding(
        self,
        artifact_id: str | UUID,
        embedding_type: str,
        embedding: list[float],
        metadata: dict | None = None,
    ) -> dict:
        """Store an embedding for an artifact.
        
        API Reference
        -------------
        POST /embeddings
        
        See: {docs_url}#/Embeddings/create_embedding_embeddings_post
        
        Request Headers:
            X-Tenant-ID: int (required)
        
        Request Body (EmbeddingCreate):
            artifact_id: UUID - Artifact to embed
            embedding_type: str - Type code (e.g., "nomic")
            embedding: list[float] - Vector values
            metadata: dict | None - Optional metadata
        
        Response (EmbeddingResponse):
            id: UUID
            artifact_id, embedding_type
            created_at: datetime
        
        Parameters
        ----------
        artifact_id : str or UUID
            Artifact to embed
        embedding_type : str
            Embedding type code (must exist)
        embedding : list[float]
            Vector values (dimensions must match type)
        metadata : dict, optional
            Additional metadata
        
        Returns
        -------
        dict
            Created embedding data (vector not returned)
        """
        response = await self._http.post(
            "/embeddings",
            headers=self._headers(require_tenant=True),
            json={
                "artifact_id": str(artifact_id),
                "embedding_type": embedding_type,
                "embedding": embedding,
                "metadata": metadata,
            },
        )
        return await self._handle_response(response, "/embeddings")
    
    async def find_similar(
        self,
        query_vector: list[float],
        embedding_type: str,
        limit: int = 10,
        min_similarity: float | None = None,
    ) -> dict:
        """Find similar embeddings by vector similarity.
        
        API Reference
        -------------
        POST /embeddings/similar
        
        See: {docs_url}#/Embeddings/find_similar_embeddings_similar_post
        
        Request Headers:
            X-Tenant-ID: int (required)
        
        Request Body (SimilarityQuery):
            query_vector: list[float] - Query vector
            embedding_type: str - Type to search
            limit: int - Maximum results (default: 10)
            min_similarity: float | None - Minimum threshold
        
        Response:
            results: list[SimilarityResult]
                - artifact_id: UUID
                - similarity: float
            total: int
        
        Parameters
        ----------
        query_vector : list[float]
            Query embedding vector
        embedding_type : str
            Embedding type to search
        limit : int
            Maximum results (default: 10)
        min_similarity : float, optional
            Minimum similarity threshold
        
        Returns
        -------
        dict
            Similarity results with artifact IDs and scores
        """
        body = {
            "query_vector": query_vector,
            "embedding_type": embedding_type,
            "limit": limit,
        }
        if min_similarity is not None:
            body["min_similarity"] = min_similarity
        
        response = await self._http.post(
            "/embeddings/similar",
            headers=self._headers(require_tenant=True),
            json=body,
        )
        return await self._handle_response(response, "/embeddings/similar")
    
    # =========================================================================
    # Embedding Types
    # =========================================================================
    
    async def create_embedding_type(
        self,
        code: str,
        display_name: str,
        provider: str,
        dimensions: int,
        distance_metric: str = "cosine",
        description: str | None = None,
    ) -> dict:
        """Create a new embedding type.
        
        API Reference
        -------------
        POST /embedding-types
        
        See: {docs_url}#/Embedding_Types/create_embedding_type_embedding_types_post
        
        Request Body (EmbeddingTypeCreate):
            code: str - Unique identifier
            display_name: str - Human name
            provider: str - Provider name (e.g., "ollama", "openai")
            dimensions: int - Vector dimensions
            distance_metric: str - Metric (default: "cosine")
            description: str | None - Optional description
        
        Note: Creates a vector table `mimir_vectors.vec_{code}`.
        
        Parameters
        ----------
        code : str
            Unique identifier for the embedding type
        display_name : str
            Human-readable name
        provider : str
            Provider name (e.g., "ollama", "openai")
        dimensions : int
            Number of vector dimensions
        distance_metric : str
            Distance metric (default: "cosine")
        description : str, optional
            Optional description
        
        Returns
        -------
        dict
            Created embedding type data
        """
        response = await self._http.post(
            "/embedding-types",
            headers={"Content-Type": "application/json"},
            json={
                "code": code,
                "display_name": display_name,
                "provider": provider,
                "dimensions": dimensions,
                "distance_metric": distance_metric,
                "description": description,
            },
        )
        return await self._handle_response(response, "/embedding-types")
    
    async def list_embedding_types(self) -> dict:
        """List all embedding types.
        
        API Reference
        -------------
        GET /embedding-types
        
        See: {docs_url}#/Embedding_Types/list_embedding_types_embedding_types_get
        
        Response:
            items: list[EmbeddingTypeResponse]
            total: int
        
        Returns
        -------
        dict
            List of embedding types
        """
        response = await self._http.get("/embedding-types")
        return await self._handle_response(response, "/embedding-types")