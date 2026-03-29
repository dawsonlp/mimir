"""Pydantic models for Mímir API responses.

These are lightweight client-side models that mirror the server's response schemas.
They provide type safety, IDE autocomplete, and serialization support.

IMPORTANT: These models MUST match the server schemas in backend/src/mimir/schemas/.
When the server schema changes, these models must be updated to match.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

# --- Tenants ---


class Tenant(BaseModel):
    """Tenant response model. Mirrors backend TenantResponse."""

    id: int
    shortname: str
    name: str
    tenant_type: str = "environment"
    description: str | None = None
    is_active: bool = True
    metadata: dict | None = None
    created_at: datetime

    model_config = {"extra": "allow"}


class TenantList(BaseModel):
    """Paginated tenant list."""

    items: list[Tenant]
    total: int


# --- Artifact Types ---


class ArtifactType(BaseModel):
    """Artifact type response model. Mirrors backend ArtifactTypeResponse.

    Note: Primary key is ``code`` (text), not an integer id.
    """

    code: str
    display_name: str
    description: str | None = None
    category: str | None = None
    is_active: bool = True
    sort_order: int = 0
    created_at: datetime

    model_config = {"extra": "allow"}


class ArtifactTypeList(BaseModel):
    """Paginated artifact type list."""

    items: list[ArtifactType]
    total: int


# --- Artifacts ---


class Artifact(BaseModel):
    """Artifact response model. Mirrors backend ArtifactResponse."""

    id: UUID
    tenant_id: int
    artifact_type: str

    # Hierarchy
    parent_artifact_id: UUID | None = None

    # Positional info (for chunks, quotes, highlights)
    start_offset: int | None = None
    end_offset: int | None = None
    position_metadata: dict | None = None

    # Content
    title: str | None = None
    content: str | None = None

    # Source tracking
    source: str | None = None
    source_system: str | None = None
    external_id: str | None = None

    # Extensible
    metadata: dict | None = None
    content_hash: str | None = None
    created_at: datetime

    model_config = {"extra": "allow"}


class ArtifactList(BaseModel):
    """Paginated artifact list."""

    items: list[Artifact]
    total: int
    limit: int = 50
    offset: int = 0


# --- Relation Types ---


class RelationType(BaseModel):
    """Relation type response model. Mirrors backend RelationTypeResponse.

    Note: Primary key is ``code`` (text), not an integer id.
    """

    code: str
    display_name: str
    description: str | None = None
    inverse_code: str | None = None
    is_symmetric: bool = False
    is_active: bool = True
    sort_order: int = 0
    created_at: datetime

    model_config = {"extra": "allow"}


class RelationTypeList(BaseModel):
    """Paginated relation type list."""

    items: list[RelationType]
    total: int


# --- Relations ---


class Relation(BaseModel):
    """Relation response model. Mirrors backend RelationResponse."""

    id: UUID
    tenant_id: int
    source_id: UUID
    target_id: UUID
    relation_type: str
    confidence: float | None = None
    metadata: dict | None = None
    created_at: datetime

    model_config = {"extra": "allow"}


class RelationList(BaseModel):
    """Paginated relation list."""

    items: list[Relation]
    total: int
    limit: int = 50
    offset: int = 0


# --- Embedding Types ---


class EmbeddingType(BaseModel):
    """Embedding type response model. Mirrors backend EmbeddingTypeResponse.

    Note: Primary key is ``code`` (text), not an integer id.
    """

    code: str
    display_name: str
    provider: str
    dimensions: int
    distance_metric: str = "cosine"
    max_tokens: int | None = None
    description: str | None = None
    vector_table_name: str | None = None
    is_active: bool = True
    sort_order: int = 0
    created_at: datetime

    model_config = {"extra": "allow"}


class EmbeddingTypeList(BaseModel):
    """Paginated embedding type list."""

    items: list[EmbeddingType]
    total: int


# --- Embeddings ---


class Embedding(BaseModel):
    """Embedding response model. Mirrors backend EmbeddingResponse."""

    id: UUID
    tenant_id: int
    artifact_id: UUID
    embedding_type: str
    created_at: datetime
    metadata: dict | None = None

    model_config = {"extra": "allow"}


class EmbeddingList(BaseModel):
    """Paginated embedding list."""

    items: list[Embedding]
    total: int
    limit: int = 50
    offset: int = 0


# --- Search ---


class SearchResult(BaseModel):
    """Individual search result. Mirrors backend SearchResult."""

    artifact: Artifact
    score: float
    rank: int | None = None

    model_config = {"extra": "allow"}


class GraphScope(BaseModel):
    """Graph traversal scope for search."""

    root_artifact_id: UUID
    max_depth: int = 3
    relation_types: list[str] | None = None
    direction: str = "both"


class SearchResponse(BaseModel):
    """Unified search response. Mirrors backend SearchResponse."""

    results: list[SearchResult]
    total: int
    query: str | None = None
    strategy: str | None = None

    model_config = {"extra": "allow"}


# --- Context ---


class RelationPathItem(BaseModel):
    """Single step in a relation path from primary artifact to context artifact."""

    relation_type: str
    direction: str

    model_config = {"extra": "allow"}


class ContextArtifact(BaseModel):
    """An artifact in the context with relationship metadata.

    Mirrors backend ContextArtifact schema.
    """

    artifact: Artifact
    relation_path: list[RelationPathItem] = Field(default_factory=list)
    distance: int
    relevance_score: float | None = None
    inclusion_reason: str | None = None

    model_config = {"extra": "allow"}


class ContextHintsApplied(BaseModel):
    """Summary of how hints affected context results."""

    query_provided: bool = False
    token_budget_enforced: bool = False
    temporal_filter_applied: bool = False
    relevance_filtering_applied: bool = False
    exclusions_applied: int = 0

    model_config = {"extra": "allow"}


class ContextMetadata(BaseModel):
    """Metadata about the context retrieval operation."""

    depth_used: int
    artifact_count: int
    tokens_estimated: int | None = None
    artifacts_excluded: int = 0

    model_config = {"extra": "allow"}


class ContextResponse(BaseModel):
    """RAG context assembly response. Mirrors backend ContextResponse.

    Contains the primary artifact and contextually relevant artifacts
    assembled according to the specified policy.
    """

    artifact: Artifact
    context: list[ContextArtifact] = Field(default_factory=list)
    policy: str
    hints_applied: ContextHintsApplied = Field(default_factory=ContextHintsApplied)
    metadata: ContextMetadata | None = None

    model_config = {"extra": "allow"}


# --- Provenance ---


class ProvenanceEvent(BaseModel):
    """Provenance event response model. Mirrors backend ProvenanceEventResponse."""

    id: UUID
    tenant_id: int
    entity_type: str
    entity_id: UUID
    action: str = "create"
    actor_type: str
    actor_id: str | None = None
    reason: str | None = None
    metadata: dict | None = None
    created_at: datetime

    model_config = {"extra": "allow"}


class ProvenanceList(BaseModel):
    """Paginated provenance list."""

    items: list[ProvenanceEvent]
    total: int
    limit: int = 50
    offset: int = 0


# --- Health ---


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    version: str

    model_config = {"extra": "allow"}
