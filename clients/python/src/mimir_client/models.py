"""Pydantic models for Mímir API responses.

These are lightweight client-side models that mirror the server's response schemas.
They provide type safety, IDE autocomplete, and serialization support.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


# --- Tenants ---


class Tenant(BaseModel):
    """Tenant response model."""

    id: int
    shortname: str
    name: str
    tenant_type: str
    description: str | None = None
    is_active: bool = True
    metadata: dict | None = None
    created_at: datetime
    updated_at: datetime


class TenantList(BaseModel):
    """Paginated tenant list."""

    items: list[Tenant]
    total: int


# --- Artifact Types ---


class ArtifactType(BaseModel):
    """Artifact type response model."""

    id: int
    code: str
    display_name: str
    description: str | None = None
    category: str | None = None
    is_active: bool = True
    sort_order: int | None = None
    created_at: datetime


class ArtifactTypeList(BaseModel):
    """Paginated artifact type list."""

    items: list[ArtifactType]
    total: int


# --- Artifacts ---


class Artifact(BaseModel):
    """Artifact response model."""

    id: UUID
    tenant_id: int
    artifact_type_id: int
    artifact_type: str
    title: str | None = None
    content: str | None = None
    source: str | None = None
    source_system: str | None = None
    external_id: str | None = None
    parent_artifact_id: UUID | None = None
    metadata: dict | None = None
    created_at: datetime
    updated_at: datetime


class ArtifactList(BaseModel):
    """Paginated artifact list."""

    items: list[Artifact]
    total: int


# --- Relation Types ---


class RelationType(BaseModel):
    """Relation type response model."""

    id: int
    code: str
    display_name: str
    description: str | None = None
    inverse_code: str | None = None
    is_active: bool = True
    sort_order: int | None = None
    created_at: datetime


class RelationTypeList(BaseModel):
    """Paginated relation type list."""

    items: list[RelationType]
    total: int


# --- Relations ---


class Relation(BaseModel):
    """Relation response model."""

    id: UUID
    tenant_id: int
    source_id: UUID
    target_id: UUID
    relation_type: str
    confidence: float | None = None
    metadata: dict | None = None
    created_at: datetime


class RelationList(BaseModel):
    """Paginated relation list."""

    items: list[Relation]
    total: int


# --- Embedding Types ---


class EmbeddingType(BaseModel):
    """Embedding type response model."""

    id: int
    code: str
    display_name: str
    provider: str
    model_name: str | None = None
    dimensions: int
    is_active: bool = True
    created_at: datetime


class EmbeddingTypeList(BaseModel):
    """Paginated embedding type list."""

    items: list[EmbeddingType]
    total: int


# --- Embeddings ---


class Embedding(BaseModel):
    """Embedding response model."""

    id: UUID
    artifact_id: UUID
    embedding_type: str
    dimensions: int | None = None
    created_at: datetime


class EmbeddingList(BaseModel):
    """Paginated embedding list."""

    items: list[Embedding]
    total: int


# --- Search ---


class SearchResult(BaseModel):
    """Individual search result."""

    artifact: Artifact
    score: float | None = None
    rank: int | None = None


class GraphScope(BaseModel):
    """Graph traversal scope for search."""

    root_artifact_id: UUID
    max_depth: int = 2
    relation_types: list[str] | None = None
    direction: str = "outgoing"


class SearchResponse(BaseModel):
    """Unified search response."""

    results: list[SearchResult]
    strategy: str
    total: int
    limit: int
    offset: int


# --- Context ---


class ContextArtifact(BaseModel):
    """Artifact within a context response."""

    id: UUID
    artifact_type: str
    title: str | None = None
    content: str | None = None
    source: str | None = None
    metadata: dict | None = None
    depth: int | None = None

    model_config = {"extra": "allow"}


class ContextRelation(BaseModel):
    """Relation within a context response."""

    source_id: UUID
    target_id: UUID
    relation_type: str

    model_config = {"extra": "allow"}


class ContextResponse(BaseModel):
    """RAG context assembly response."""

    root_artifact_id: UUID
    policy: str
    artifacts: list[ContextArtifact]
    relations: list[ContextRelation]
    total_artifacts: int
    max_depth: int | None = None

    model_config = {"extra": "allow"}


# --- Provenance ---


class ProvenanceEvent(BaseModel):
    """Provenance event response model."""

    id: UUID
    tenant_id: int
    artifact_id: UUID
    event_type: str
    actor: str | None = None
    source_system: str | None = None
    description: str | None = None
    metadata: dict | None = None
    created_at: datetime


class ProvenanceList(BaseModel):
    """Paginated provenance list."""

    items: list[ProvenanceEvent]
    total: int


# --- Health ---


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    version: str

    model_config = {"extra": "allow"}