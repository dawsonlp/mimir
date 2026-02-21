"""mimir-client — Official Python client for the Mímir Knowledge Graph API."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("mimir-client")
except PackageNotFoundError:
    __version__ = "dev"

from mimir_client.client import MimirClient
from mimir_client.config import MimirClientSettings, get_settings
from mimir_client.exceptions import (
    MimirConflictError,
    MimirConnectionError,
    MimirError,
    MimirNotFoundError,
    MimirServerError,
    MimirValidationError,
)
from mimir_client.models import (
    Artifact,
    ArtifactList,
    ArtifactType,
    ArtifactTypeList,
    ContextArtifact,
    ContextRelation,
    ContextResponse,
    Embedding,
    EmbeddingList,
    EmbeddingType,
    EmbeddingTypeList,
    GraphScope,
    HealthResponse,
    ProvenanceEvent,
    ProvenanceList,
    Relation,
    RelationList,
    RelationType,
    RelationTypeList,
    SearchResponse,
    SearchResult,
    Tenant,
    TenantList,
)

__all__ = [
    # Client
    "MimirClient",
    "MimirClientSettings",
    "get_settings",
    # Exceptions
    "MimirError",
    "MimirConnectionError",
    "MimirNotFoundError",
    "MimirConflictError",
    "MimirValidationError",
    "MimirServerError",
    # Models
    "Tenant",
    "TenantList",
    "ArtifactType",
    "ArtifactTypeList",
    "Artifact",
    "ArtifactList",
    "RelationType",
    "RelationTypeList",
    "Relation",
    "RelationList",
    "EmbeddingType",
    "EmbeddingTypeList",
    "Embedding",
    "EmbeddingList",
    "SearchResult",
    "SearchResponse",
    "GraphScope",
    "ContextArtifact",
    "ContextRelation",
    "ContextResponse",
    "ProvenanceEvent",
    "ProvenanceList",
    "HealthResponse",
]
