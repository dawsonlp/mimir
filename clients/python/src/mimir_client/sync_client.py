"""MimirSyncClient — synchronous HTTP client for the Mímir Knowledge Graph API (v5).

Drop-in synchronous alternative to ``MimirClient``. Uses ``httpx.Client`` (sync)
internally, so no event loop threading or async bridges are needed.

Usage:
    with MimirSyncClient(api_url="http://localhost:38000", tenant_id=1) as client:
        tenant = client.get_tenant(1)
        artifacts = client.list_artifacts(artifact_type="document")

Or with settings from environment:
    from mimir_client.config import get_settings
    with MimirSyncClient.from_settings(get_settings()) as client:
        ...
"""

from __future__ import annotations

from uuid import UUID

import httpx

from mimir_client.config import MimirClientSettings
from mimir_client.exceptions import (
    MimirConnectionError,
    MimirError,
    MimirNotFoundError,
    MimirConflictError,
    MimirServerError,
    MimirValidationError,
)
from mimir_client.models import (
    Artifact,
    ArtifactList,
    ArtifactType,
    ArtifactTypeList,
    ContextResponse,
    Embedding,
    EmbeddingList,
    EmbeddingType,
    EmbeddingTypeList,
    GraphScope,
    HealthResponse,
    ProvenanceList,
    Relation,
    RelationList,
    RelationType,
    RelationTypeList,
    SearchResponse,
    Tenant,
    TenantList,
)


class MimirSyncClient:
    """Synchronous HTTP client for the Mímir Knowledge Graph API.

    Provides the same API surface as :class:`MimirClient` but with blocking
    calls. Uses ``httpx.Client`` internally — no event loop required.

    Args:
        api_url: Base URL of the Mímir API (e.g. ``http://localhost:38000``).
        tenant_id: Default tenant ID injected as ``X-Tenant-ID`` header.
            Can be ``None`` for tenant management calls only.
        timeout: Request timeout in seconds.
    """

    def __init__(
        self,
        api_url: str = "http://localhost:38000",
        tenant_id: int | None = None,
        timeout: float = 30.0,
    ):
        self._api_url = api_url.rstrip("/")
        self._tenant_id = tenant_id
        self._timeout = timeout
        headers = {}
        if tenant_id is not None:
            headers["X-Tenant-ID"] = str(tenant_id)
        self._client = httpx.Client(
            base_url=self._api_url,
            headers=headers,
            timeout=timeout,
        )

    @classmethod
    def from_settings(cls, settings: MimirClientSettings) -> MimirSyncClient:
        """Create a client from a ``MimirClientSettings`` instance."""
        return cls(
            api_url=settings.api_url,
            tenant_id=settings.tenant_id,
            timeout=settings.timeout,
        )

    @property
    def tenant_id(self) -> int | None:
        return self._tenant_id

    @tenant_id.setter
    def tenant_id(self, value: int | None):
        self._tenant_id = value
        if value is not None:
            self._client.headers["X-Tenant-ID"] = str(value)
        else:
            self._client.headers.pop("X-Tenant-ID", None)

    def close(self):
        """Close the underlying HTTP client."""
        self._client.close()

    def __enter__(self) -> MimirSyncClient:
        return self

    def __exit__(self, *args):
        self.close()

    # ── Internal request handling ──────────────────────────────────────

    def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        """Execute an HTTP request with error mapping."""
        try:
            response = self._client.request(method, path, **kwargs)
        except httpx.ConnectError as exc:
            raise MimirConnectionError(f"Cannot connect to {self._api_url}") from exc
        except httpx.TimeoutException as exc:
            raise MimirConnectionError(f"Request timed out: {method} {path}") from exc

        if response.status_code < 400:
            return response

        # Extract error detail
        try:
            body = response.json()
            detail = body.get("detail", response.text)
        except Exception:
            detail = response.text

        status = response.status_code
        if status == 404:
            raise MimirNotFoundError(detail)
        elif status == 409:
            raise MimirConflictError(detail)
        elif status == 422:
            raise MimirValidationError(detail)
        elif status >= 500:
            raise MimirServerError(detail)
        else:
            raise MimirError(f"HTTP {status}: {detail}")

    def _get(self, path: str, **kwargs) -> httpx.Response:
        return self._request("GET", path, **kwargs)

    def _post(self, path: str, **kwargs) -> httpx.Response:
        return self._request("POST", path, **kwargs)

    def _patch(self, path: str, **kwargs) -> httpx.Response:
        return self._request("PATCH", path, **kwargs)

    def _delete(self, path: str, **kwargs) -> httpx.Response:
        return self._request("DELETE", path, **kwargs)

    # ── Tenants ────────────────────────────────────────────────────────

    def create_tenant(
        self,
        shortname: str,
        name: str,
        *,
        tenant_type: str = "environment",
        description: str | None = None,
        metadata: dict | None = None,
    ) -> Tenant:
        """Create a new tenant."""
        body: dict = {
            "shortname": shortname,
            "name": name,
            "tenant_type": tenant_type,
        }
        if description is not None:
            body["description"] = description
        if metadata is not None:
            body["metadata"] = metadata
        resp = self._post("/tenants", json=body)
        return Tenant.model_validate(resp.json())

    def get_tenant(self, tenant_id: int) -> Tenant:
        """Get a tenant by ID."""
        resp = self._get(f"/tenants/{tenant_id}")
        return Tenant.model_validate(resp.json())

    def get_tenant_by_shortname(self, shortname: str) -> Tenant:
        """Get a tenant by shortname."""
        resp = self._get(f"/tenants/by-shortname/{shortname}")
        return Tenant.model_validate(resp.json())

    def list_tenants(self, *, active_only: bool = True) -> TenantList:
        """List tenants."""
        resp = self._get("/tenants", params={"active_only": active_only})
        return TenantList.model_validate(resp.json())

    def update_tenant(self, tenant_id: int, **fields) -> Tenant:
        """Update a tenant. Accepts: name, description, is_active, metadata."""
        resp = self._patch(f"/tenants/{tenant_id}", json=fields)
        return Tenant.model_validate(resp.json())

    def delete_tenant(self, tenant_id: int) -> None:
        """Delete a tenant and CASCADE all associated data. No undo."""
        self._delete(f"/tenants/{tenant_id}")

    def ensure_tenant(
        self,
        shortname: str = "dev",
        name: str = "Development",
    ) -> Tenant:
        """Ensure a tenant exists. Returns existing or creates new.

        Updates the client's ``tenant_id`` to match.
        """
        try:
            tenant = self.get_tenant_by_shortname(shortname)
            self.tenant_id = tenant.id
            return tenant
        except MimirNotFoundError:
            pass

        tenant = self.create_tenant(shortname, name)
        self.tenant_id = tenant.id
        return tenant

    # ── Artifact Types ─────────────────────────────────────────────────

    def create_artifact_type(
        self,
        code: str,
        display_name: str,
        *,
        description: str | None = None,
        category: str | None = None,
        is_active: bool = True,
        sort_order: int | None = None,
    ) -> ArtifactType:
        """Register a new artifact type."""
        body: dict = {"code": code, "display_name": display_name, "is_active": is_active}
        if description is not None:
            body["description"] = description
        if category is not None:
            body["category"] = category
        if sort_order is not None:
            body["sort_order"] = sort_order
        resp = self._post("/artifact-types", json=body)
        return ArtifactType.model_validate(resp.json())

    def get_artifact_type(self, code: str) -> ArtifactType:
        """Get an artifact type by code."""
        resp = self._get(f"/artifact-types/{code}")
        return ArtifactType.model_validate(resp.json())

    def list_artifact_types(
        self, *, active_only: bool = True, category: str | None = None
    ) -> ArtifactTypeList:
        """List artifact types."""
        params: dict = {"active_only": active_only}
        if category is not None:
            params["category"] = category
        resp = self._get("/artifact-types", params=params)
        return ArtifactTypeList.model_validate(resp.json())

    def update_artifact_type(self, code: str, **fields) -> ArtifactType:
        """Update an artifact type. Accepts: display_name, description, category, is_active, sort_order."""
        resp = self._patch(f"/artifact-types/{code}", json=fields)
        return ArtifactType.model_validate(resp.json())

    def ensure_artifact_type(
        self,
        code: str,
        display_name: str | None = None,
        *,
        description: str | None = None,
        category: str | None = None,
    ) -> ArtifactType:
        """Ensure an artifact type exists. No-op if already registered."""
        try:
            return self.get_artifact_type(code)
        except MimirNotFoundError:
            pass
        return self.create_artifact_type(
            code=code,
            display_name=display_name or code.replace("_", " ").title(),
            description=description,
            category=category,
        )

    # ── Artifacts ──────────────────────────────────────────────────────

    def create_artifact(
        self,
        artifact_type: str,
        *,
        title: str | None = None,
        content: str | None = None,
        parent_artifact_id: UUID | str | None = None,
        source: str | None = None,
        source_system: str | None = None,
        external_id: str | None = None,
        metadata: dict | None = None,
    ) -> Artifact:
        """Create an artifact."""
        body: dict = {"artifact_type": artifact_type}
        if title is not None:
            body["title"] = title
        if content is not None:
            body["content"] = content
        if parent_artifact_id is not None:
            body["parent_artifact_id"] = str(parent_artifact_id)
        if source is not None:
            body["source"] = source
        if source_system is not None:
            body["source_system"] = source_system
        if external_id is not None:
            body["external_id"] = external_id
        if metadata is not None:
            body["metadata"] = metadata
        resp = self._post("/artifacts", json=body)
        return Artifact.model_validate(resp.json())

    def get_artifact(self, artifact_id: UUID | str) -> Artifact:
        """Get an artifact by ID."""
        resp = self._get(f"/artifacts/{artifact_id}")
        return Artifact.model_validate(resp.json())

    def list_artifacts(
        self,
        *,
        artifact_type: str | None = None,
        parent_artifact_id: UUID | str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> ArtifactList:
        """List artifacts with optional filters."""
        params: dict = {"limit": limit, "offset": offset}
        if artifact_type is not None:
            params["artifact_type"] = artifact_type
        if parent_artifact_id is not None:
            params["parent_artifact_id"] = str(parent_artifact_id)
        resp = self._get("/artifacts", params=params)
        return ArtifactList.model_validate(resp.json())

    def get_children(self, artifact_id: UUID | str) -> ArtifactList:
        """Get child artifacts of a given artifact."""
        resp = self._get(f"/artifacts/{artifact_id}/children")
        return ArtifactList.model_validate(resp.json())

    # ── Relation Types ─────────────────────────────────────────────────

    def create_relation_type(
        self,
        code: str,
        display_name: str,
        *,
        description: str | None = None,
        inverse_code: str | None = None,
        is_active: bool = True,
        sort_order: int | None = None,
    ) -> RelationType:
        """Register a new relation type."""
        body: dict = {"code": code, "display_name": display_name, "is_active": is_active}
        if description is not None:
            body["description"] = description
        if inverse_code is not None:
            body["inverse_code"] = inverse_code
        if sort_order is not None:
            body["sort_order"] = sort_order
        resp = self._post("/relation-types", json=body)
        return RelationType.model_validate(resp.json())

    def get_relation_type(self, code: str) -> RelationType:
        """Get a relation type by code."""
        resp = self._get(f"/relation-types/{code}")
        return RelationType.model_validate(resp.json())

    def list_relation_types(self, *, active_only: bool = True) -> RelationTypeList:
        """List relation types."""
        resp = self._get("/relation-types", params={"active_only": active_only})
        return RelationTypeList.model_validate(resp.json())

    def update_relation_type(self, code: str, **fields) -> RelationType:
        """Update a relation type. Accepts: display_name, description, inverse_code, is_active, sort_order."""
        resp = self._patch(f"/relation-types/{code}", json=fields)
        return RelationType.model_validate(resp.json())

    def get_inverse_relation_type(self, code: str) -> RelationType:
        """Get the inverse of a relation type."""
        resp = self._get(f"/relation-types/{code}/inverse")
        return RelationType.model_validate(resp.json())

    def ensure_relation_type(
        self,
        code: str,
        display_name: str | None = None,
        *,
        description: str | None = None,
        inverse_code: str | None = None,
    ) -> RelationType:
        """Ensure a relation type exists. No-op if already registered."""
        try:
            return self.get_relation_type(code)
        except MimirNotFoundError:
            pass
        return self.create_relation_type(
            code=code,
            display_name=display_name or code.replace("_", " ").title(),
            description=description,
            inverse_code=inverse_code,
        )

    # ── Relations ──────────────────────────────────────────────────────

    def create_relation(
        self,
        source_id: UUID | str,
        target_id: UUID | str,
        relation_type: str,
        *,
        confidence: float | None = None,
        metadata: dict | None = None,
    ) -> Relation:
        """Create a relation between two artifacts.

        Returns the relation. Raises ``MimirConflictError`` if the relation
        already exists (same source, target, type).
        """
        body: dict = {
            "source_id": str(source_id),
            "target_id": str(target_id),
            "relation_type": relation_type,
        }
        if confidence is not None:
            body["confidence"] = confidence
        if metadata is not None:
            body["metadata"] = metadata
        resp = self._post("/relations", json=body)
        return Relation.model_validate(resp.json())

    def get_relation(self, relation_id: UUID | str) -> Relation:
        """Get a relation by ID."""
        resp = self._get(f"/relations/{relation_id}")
        return Relation.model_validate(resp.json())

    def list_relations(
        self,
        *,
        relation_type: str | None = None,
        source_id: UUID | str | None = None,
        target_id: UUID | str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> RelationList:
        """List relations with optional filters."""
        params: dict = {"limit": limit, "offset": offset}
        if relation_type is not None:
            params["relation_type"] = relation_type
        if source_id is not None:
            params["source_id"] = str(source_id)
        if target_id is not None:
            params["target_id"] = str(target_id)
        resp = self._get("/relations", params=params)
        return RelationList.model_validate(resp.json())

    def get_artifact_relations(
        self,
        artifact_id: UUID | str,
        *,
        direction: str | None = None,
    ) -> RelationList:
        """Get all relations for an artifact.

        Args:
            artifact_id: The artifact UUID.
            direction: ``'incoming'``, ``'outgoing'``, or ``'both'`` (default).
        """
        params: dict = {}
        if direction is not None:
            params["direction"] = direction
        resp = self._get(f"/relations/artifact/{artifact_id}", params=params)
        return RelationList.model_validate(resp.json())

    # ── Embedding Types ────────────────────────────────────────────────

    def create_embedding_type(
        self,
        code: str,
        display_name: str,
        provider: str,
        dimensions: int,
        *,
        distance_metric: str = "cosine",
        max_tokens: int | None = None,
        description: str | None = None,
    ) -> EmbeddingType:
        """Register a new embedding type."""
        body: dict = {
            "code": code,
            "display_name": display_name,
            "provider": provider,
            "dimensions": dimensions,
            "distance_metric": distance_metric,
        }
        if max_tokens is not None:
            body["max_tokens"] = max_tokens
        if description is not None:
            body["description"] = description
        resp = self._post("/embedding-types", json=body)
        return EmbeddingType.model_validate(resp.json())

    def get_embedding_type(self, code: str) -> EmbeddingType:
        """Get an embedding type by code."""
        resp = self._get(f"/embedding-types/{code}")
        return EmbeddingType.model_validate(resp.json())

    def list_embedding_types(self) -> EmbeddingTypeList:
        """List all embedding types."""
        resp = self._get("/embedding-types")
        return EmbeddingTypeList.model_validate(resp.json())

    def delete_embedding_type(self, code: str) -> None:
        """Delete an embedding type by code."""
        self._delete(f"/embedding-types/{code}")

    def ensure_embedding_type(
        self,
        code: str,
        display_name: str | None = None,
        *,
        provider: str = "ollama",
        dimensions: int = 768,
        distance_metric: str = "cosine",
    ) -> EmbeddingType:
        """Ensure an embedding type exists. No-op if already registered."""
        try:
            return self.get_embedding_type(code)
        except MimirNotFoundError:
            pass
        return self.create_embedding_type(
            code=code,
            display_name=display_name or code.title(),
            provider=provider,
            dimensions=dimensions,
            distance_metric=distance_metric,
        )

    # ── Embeddings ─────────────────────────────────────────────────────

    def create_embedding(
        self,
        artifact_id: UUID | str,
        embedding_type: str,
        embedding: list[float],
    ) -> Embedding:
        """Store a pre-computed embedding vector."""
        body = {
            "artifact_id": str(artifact_id),
            "embedding_type": embedding_type,
            "embedding": embedding,
        }
        resp = self._post("/embeddings", json=body)
        return Embedding.model_validate(resp.json())

    def get_embedding(self, embedding_id: UUID | str) -> Embedding:
        """Get an embedding by ID."""
        resp = self._get(f"/embeddings/{embedding_id}")
        return Embedding.model_validate(resp.json())

    def list_embeddings(
        self,
        *,
        artifact_id: UUID | str | None = None,
        embedding_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> EmbeddingList:
        """List embeddings with optional filters."""
        params: dict = {"limit": limit, "offset": offset}
        if artifact_id is not None:
            params["artifact_id"] = str(artifact_id)
        if embedding_type is not None:
            params["embedding_type"] = embedding_type
        resp = self._get("/embeddings", params=params)
        return EmbeddingList.model_validate(resp.json())

    # ── Search ─────────────────────────────────────────────────────────

    def search(
        self,
        *,
        query: str | None = None,
        query_vector: list[float] | None = None,
        similar_to: UUID | str | None = None,
        embedding_type: str | None = None,
        limit: int = 20,
        offset: int = 0,
        artifact_types: list[str] | None = None,
        metadata_filters: dict | None = None,
        scope_artifact_id: UUID | str | None = None,
        graph_scope: GraphScope | dict | None = None,
        similarity_threshold: float | None = None,
        semantic_weight: float | None = None,
        related_to: UUID | str | None = None,
        relation_type: str | None = None,
        relation_direction: str | None = None,
    ) -> SearchResponse:
        """Unified search. Strategy is inferred from parameters:

        - ``query`` only -> fulltext
        - ``query_vector`` (+ ``embedding_type``) -> semantic
        - ``query`` + ``query_vector`` -> hybrid
        - ``similar_to`` (+ ``embedding_type``) -> similar
        """
        body: dict = {"limit": limit, "offset": offset}
        if query is not None:
            body["query"] = query
        if query_vector is not None:
            body["query_vector"] = query_vector
        if similar_to is not None:
            body["similar_to"] = str(similar_to)
        if embedding_type is not None:
            body["embedding_type"] = embedding_type
        if similarity_threshold is not None:
            body["similarity_threshold"] = similarity_threshold
        if semantic_weight is not None:
            body["semantic_weight"] = semantic_weight
        if artifact_types is not None:
            body["artifact_types"] = artifact_types
        if metadata_filters is not None:
            body["metadata_filters"] = metadata_filters
        if graph_scope is not None:
            if isinstance(graph_scope, GraphScope):
                body["graph_scope"] = graph_scope.model_dump(mode="json")
            else:
                body["graph_scope"] = graph_scope
        elif scope_artifact_id is not None:
            body["scope_artifact_id"] = str(scope_artifact_id)
        if related_to is not None:
            body["related_to"] = str(related_to)
        if relation_type is not None:
            body["relation_type"] = relation_type
        if relation_direction is not None:
            body["relation_direction"] = relation_direction
        resp = self._post("/search", json=body)
        return SearchResponse.model_validate(resp.json())

    def search_fulltext(
        self,
        query: str,
        *,
        limit: int = 20,
        offset: int = 0,
        artifact_types: list[str] | None = None,
        metadata_filters: dict | None = None,
        scope_artifact_id: UUID | str | None = None,
    ) -> SearchResponse:
        """Fulltext search convenience method (uses unified search)."""
        return self.search(
            query=query,
            limit=limit,
            offset=offset,
            artifact_types=artifact_types,
            metadata_filters=metadata_filters,
            scope_artifact_id=scope_artifact_id,
        )

    def search_semantic(
        self,
        query_vector: list[float],
        embedding_type: str,
        *,
        limit: int = 20,
        offset: int = 0,
        similarity_threshold: float | None = None,
        artifact_types: list[str] | None = None,
        metadata_filters: dict | None = None,
        scope_artifact_id: UUID | str | None = None,
        graph_scope: GraphScope | dict | None = None,
    ) -> SearchResponse:
        """Semantic (vector) search convenience method.

        Requires a pre-computed query vector. For automatic embedding
        generation from text, use ``mimir-semantic`` instead.
        """
        return self.search(
            query_vector=query_vector,
            embedding_type=embedding_type,
            limit=limit,
            offset=offset,
            similarity_threshold=similarity_threshold,
            artifact_types=artifact_types,
            metadata_filters=metadata_filters,
            scope_artifact_id=scope_artifact_id,
            graph_scope=graph_scope,
        )

    def search_hybrid(
        self,
        query: str,
        query_vector: list[float],
        embedding_type: str,
        *,
        limit: int = 20,
        offset: int = 0,
        semantic_weight: float | None = None,
        similarity_threshold: float | None = None,
        artifact_types: list[str] | None = None,
        metadata_filters: dict | None = None,
        scope_artifact_id: UUID | str | None = None,
        graph_scope: GraphScope | dict | None = None,
    ) -> SearchResponse:
        """Hybrid (fulltext + vector) search convenience method.

        Combines keyword matching with vector similarity. Requires a
        pre-computed query vector. For automatic embedding generation
        from text, use ``mimir-semantic`` instead.
        """
        return self.search(
            query=query,
            query_vector=query_vector,
            embedding_type=embedding_type,
            limit=limit,
            offset=offset,
            semantic_weight=semantic_weight,
            similarity_threshold=similarity_threshold,
            artifact_types=artifact_types,
            metadata_filters=metadata_filters,
            scope_artifact_id=scope_artifact_id,
            graph_scope=graph_scope,
        )

    def search_similar(
        self,
        artifact_id: UUID | str,
        embedding_type: str,
        *,
        limit: int = 20,
        similarity_threshold: float | None = None,
        artifact_types: list[str] | None = None,
    ) -> SearchResponse:
        """Find artifacts similar to a given artifact.

        Uses the existing embedding of the specified artifact
        to find similar items.
        """
        return self.search(
            similar_to=artifact_id,
            embedding_type=embedding_type,
            limit=limit,
            similarity_threshold=similarity_threshold,
            artifact_types=artifact_types,
        )

    # ── Context / RAG Assembly ─────────────────────────────────────────

    def get_context(
        self,
        artifact_id: UUID | str,
        *,
        policy: str = "full_graph",
        max_depth: int | None = None,
        max_tokens: int | None = None,
        include_embeddings: bool = False,
        embedding_type: str | None = None,
        preferences: dict | None = None,
    ) -> ContextResponse:
        """Retrieve assembled RAG context for an artifact.

        Args:
            artifact_id: The root artifact UUID.
            policy: Context policy — ``'direct_relations'``, ``'derived_lineage'``,
                ``'evidence_chain'``, or ``'full_graph'``.
            max_depth: Maximum traversal depth.
            max_tokens: Token budget for context assembly.
            include_embeddings: Whether to include embedding vectors.
            embedding_type: Required if ``include_embeddings`` is True.
            preferences: Additional context preferences dict.
        """
        body: dict = {"policy": policy}
        if max_depth is not None:
            body["max_depth"] = max_depth
        if max_tokens is not None:
            body["max_tokens"] = max_tokens
        if include_embeddings:
            body["include_embeddings"] = True
        if embedding_type is not None:
            body["embedding_type"] = embedding_type
        if preferences is not None:
            body["preferences"] = preferences
        resp = self._post(f"/context/{artifact_id}", json=body)
        return ContextResponse.model_validate(resp.json())

    # ── Provenance ─────────────────────────────────────────────────────

    def list_provenance_by_artifact(
        self,
        artifact_id: UUID | str,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> ProvenanceList:
        """List provenance events for an artifact."""
        params: dict = {"limit": limit, "offset": offset}
        resp = self._get(f"/provenance/artifact/{artifact_id}", params=params)
        return ProvenanceList.model_validate(resp.json())

    def list_provenance(
        self,
        *,
        entity_type: str | None = None,
        entity_id: UUID | str | None = None,
        actor_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> ProvenanceList:
        """List provenance events with optional filters.

        Args:
            entity_type: Filter by entity type (artifact, relation, embedding).
            entity_id: Filter by entity UUID.
            actor_type: Filter by actor type (user, system, llm, api_client, migration).
            limit: Maximum results.
            offset: Pagination offset.
        """
        params: dict = {"limit": limit, "offset": offset}
        if entity_type is not None:
            params["entity_type"] = entity_type
        if entity_id is not None:
            params["entity_id"] = str(entity_id)
        if actor_type is not None:
            params["actor_type"] = actor_type
        resp = self._get("/provenance", params=params)
        return ProvenanceList.model_validate(resp.json())

    # ── Health ─────────────────────────────────────────────────────────

    def health(self) -> HealthResponse:
        """Check API health. Returns the health response."""
        resp = self._get("/health")
        return HealthResponse.model_validate(resp.json())

    def is_healthy(self) -> bool:
        """Check if the API is healthy. Returns True/False without raising."""
        try:
            h = self.health()
            return h.status == "healthy"
        except Exception:
            return False