"""Pydantic schemas for Artifact entity - the universal knowledge unit.

Artifact is the core entity in Mímir V3. ALL knowledge is stored as artifacts
with type discrimination via artifact_type.

V2 Changes:
- UUID primary keys (client-generated UUIDv7 preferred)
- Append-only (no update schema)
- No version table (each artifact is its own identity)
- Supersedes relation for versioning (editorial intent)

Artifact Type Categories:
- Content: conversation, document, note (primary source material)
- Positional: chunk, quote, highlight, annotation (references within content)
- Derived: intent, decision, analysis, summary, finding, question, answer

Hierarchy:
- Use parent_artifact_id for tree structures (document → chunks)
- Positional types use start_offset/end_offset for character positions

Related Entities:
- Relation: Connects artifacts (derived_from, supports, supersedes)
- Embedding: Vector representation for semantic search

Usage Examples:
    # Document (server generates UUID)
    POST /artifacts {"artifact_type": "document", "title": "Report", "content": "..."}
    
    # Decision with client-generated UUID
    POST /artifacts {"id": "01926a5c-...", "artifact_type": "decision", 
                     "title": "Use PostgreSQL", "content": "..."}
    
    # Chunk with position
    POST /artifacts {"artifact_type": "chunk", "parent_artifact_id": "...",
                     "start_offset": 0, "end_offset": 500, "content": "..."}
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ArtifactBase(BaseModel):
    """Base schema for artifact."""

    artifact_type: str = Field(..., description="Type from artifact_type vocabulary")
    parent_artifact_id: UUID | None = Field(None, description="Parent artifact for hierarchy")
    
    # Positional info (for chunks, quotes, highlights)
    start_offset: int | None = Field(None, description="Character position start")
    end_offset: int | None = Field(None, description="Character position end")
    position_metadata: dict | None = Field(None, description="Page, line, paragraph info")
    
    # Content
    title: str | None = Field(None, description="Title or label")
    content: str | None = Field(None, description="Main content")
    
    # Source tracking
    source: str | None = Field(None, description="Origin: import, manual, generated")
    source_system: str | None = Field(None, description="External system: chatgpt, notion")
    external_id: str | None = Field(None, description="ID in source system")
    
    # Extensible
    metadata: dict | None = Field(default_factory=dict, description="Additional metadata")


class ArtifactCreate(BaseModel):
    """Schema for creating a new artifact.
    
    id is optional - if provided, must be a valid UUID (UUIDv7 preferred).
    If omitted, server generates a UUID.
    """

    id: UUID | None = Field(None, description="Optional client-generated UUID (UUIDv7 preferred)")
    artifact_type: str = Field(..., min_length=1, max_length=50)
    parent_artifact_id: UUID | None = None
    
    # Positional
    start_offset: int | None = None
    end_offset: int | None = None
    position_metadata: dict | None = None
    
    # Content
    title: str | None = None
    content: str | None = None
    
    # Source
    source: str | None = None
    source_system: str | None = None
    external_id: str | None = None
    
    metadata: dict | None = None


# NOTE: ArtifactUpdate removed - artifacts are append-only


class ArtifactResponse(ArtifactBase):
    """Schema for artifact response."""

    id: UUID
    tenant_id: int
    content_hash: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ArtifactListResponse(BaseModel):
    """Schema for listing artifacts."""

    items: list[ArtifactResponse]
    total: int
    limit: int = 50
    offset: int = 0


# NOTE: ArtifactVersion schemas removed - each artifact is its own identity
# Use supersedes relation for versioning (editorial intent)

# NOTE: SoftDeleteResponse and PhysicalDeleteResponse removed
# Artifacts are append-only; cleanup via tenant-level deletion (FK CASCADE)
