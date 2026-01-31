"""Pydantic schemas for Mímir V2 API."""

from mimir.schemas.artifact import (
    ArtifactBase,
    ArtifactCreate,
    ArtifactListResponse,
    ArtifactResponse,
)
from mimir.schemas.artifact_type import (
    ArtifactTypeCreate,
    ArtifactTypeListResponse,
    ArtifactTypeResponse,
    ArtifactTypeUpdate,
)
from mimir.schemas.embedding import (
    EmbeddingCreate,
    EmbeddingListResponse,
    EmbeddingResponse,
    EmbeddingWithVectorResponse,
    SimilaritySearchRequest,
    SimilaritySearchResponse,
)
from mimir.schemas.embedding_type import (
    EmbeddingTypeCreate,
    EmbeddingTypeListResponse,
    EmbeddingTypeResponse,
)
from mimir.schemas.provenance import (
    ProvenanceEventCreate,
    ProvenanceEventListResponse,
    ProvenanceEventResponse,
)
from mimir.schemas.relation import (
    RelationCreate,
    RelationListResponse,
    RelationResponse,
)
from mimir.schemas.relation_type import (
    RelationTypeCreate,
    RelationTypeListResponse,
    RelationTypeResponse,
    RelationTypeUpdate,
)
from mimir.schemas.search import (
    FulltextSearchQuery,
    HybridSearchQuery,
    SearchQuery,
    SearchResponse,
    SearchResult,
    SemanticSearchQuery,
    SimilaritySearchRequest,
)
from mimir.schemas.tenant import (
    TenantCreate,
    TenantListResponse,
    TenantResponse,
    TenantUpdate,
)

__all__ = [
    # Tenant
    "TenantCreate",
    "TenantUpdate",
    "TenantResponse",
    "TenantListResponse",
    # Artifact (V2: append-only, no updates or versions)
    "ArtifactBase",
    "ArtifactCreate",
    "ArtifactResponse",
    "ArtifactListResponse",
    # Artifact Type
    "ArtifactTypeCreate",
    "ArtifactTypeUpdate",
    "ArtifactTypeResponse",
    "ArtifactTypeListResponse",
    # Relation (V2: append-only)
    "RelationCreate",
    "RelationResponse",
    "RelationListResponse",
    # Relation Type
    "RelationTypeCreate",
    "RelationTypeUpdate",
    "RelationTypeResponse",
    "RelationTypeListResponse",
    # Embedding Type
    "EmbeddingTypeCreate",
    "EmbeddingTypeResponse",
    "EmbeddingTypeListResponse",
    # Embedding (V2: append-only, multi-table)
    "EmbeddingCreate",
    "EmbeddingResponse",
    "EmbeddingWithVectorResponse",
    "EmbeddingListResponse",
    "SimilaritySearchRequest",
    "SimilaritySearchResponse",
    # Search
    "SearchQuery",
    "SemanticSearchQuery",
    "FulltextSearchQuery",
    "HybridSearchQuery",
    "SearchResult",
    "SearchResponse",
    "SimilaritySearchRequest",
    # Provenance (V2: append-only)
    "ProvenanceEventCreate",
    "ProvenanceEventResponse",
    "ProvenanceEventListResponse",
]
