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
    MimirTenantError,
    MimirValidationError,
)
from mimir_client.models import (
    Artifact,
    ArtifactList,
    ArtifactType,
    ArtifactTypeList,
    ContextArtifact,
    ContextHintsApplied,
    ContextMetadata,
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
    RelationPathItem,
    RelationType,
    RelationTypeList,
    SearchResponse,
    SearchResult,
    Tenant,
    TenantList,
)
from mimir_client.sync_client import MimirSyncClient

__all__ = [
    # Client
    "MimirClient",
    "MimirSyncClient",
    "MimirClientSettings",
    "get_settings",
    # Exceptions
    "MimirError",
    "MimirConnectionError",
    "MimirNotFoundError",
    "MimirConflictError",
    "MimirValidationError",
    "MimirServerError",
    "MimirTenantError",
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
    "RelationPathItem",
    "ContextArtifact",
    "ContextHintsApplied",
    "ContextMetadata",
    "ContextResponse",
    "ProvenanceEvent",
    "ProvenanceList",
    "HealthResponse",
]
