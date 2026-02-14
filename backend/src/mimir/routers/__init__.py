"""Routers for Mímir V3 API."""

from mimir.routers import (
    artifact_types,
    artifacts,
    context,
    embedding_types,
    embeddings,
    provenance,
    relation_types,
    relations,
    search,
    tenants,
)

__all__ = [
    "tenants",
    "artifact_types",
    "artifacts",
    "context",
    "relation_types",
    "relations",
    "embedding_types",
    "embeddings",
    "search",
    "provenance",
]
