"""Pydantic schemas for Context Retrieval Service.

The Context Retrieval Service enables RAG applications to retrieve an artifact
along with all contextually relevant artifacts in a single operation. Context
assembly is policy-driven and extensible.

Context Policies:
- direct_relations: Include artifacts directly connected by any relation
- derived_lineage: Include source and all derived artifacts (follow derived_from chain)
- evidence_chain: Include supporting evidence (follow supports chain)
- full_graph: All connected artifacts within N hops

This is a separate domain concern from artifact/relation storage.
"""

from datetime import date
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field

from mimir.schemas.artifact import ArtifactResponse


class ContextPolicy(str, Enum):
    """Available context assembly policies."""
    
    DIRECT_RELATIONS = "direct_relations"
    DERIVED_LINEAGE = "derived_lineage"
    EVIDENCE_CHAIN = "evidence_chain"
    FULL_GRAPH = "full_graph"


class RelationDirection(str, Enum):
    """Direction of relation from traversal perspective."""
    
    OUTGOING = "outgoing"
    INCOMING = "incoming"


class RelationPathItem(BaseModel):
    """Single step in the relation path from primary artifact to context artifact."""
    
    relation_type: str = Field(..., description="Type of relation (e.g., derived_from)")
    direction: RelationDirection = Field(..., description="Direction from path traversal perspective")


class ContextArtifact(BaseModel):
    """An artifact in the context with relationship metadata."""
    
    artifact: ArtifactResponse = Field(..., description="The context artifact")
    relation_path: list[RelationPathItem] = Field(
        default_factory=list,
        description="Path of relations from primary artifact to this artifact"
    )
    distance: int = Field(..., description="Number of hops from primary artifact")
    relevance_score: float | None = Field(None, description="Semantic relevance to query (0.0-1.0)")
    inclusion_reason: str = Field(..., description="Why this artifact was included")


# ============================================================================
# Context Hints (Request Body)
# ============================================================================

class TemporalMode(str, Enum):
    """Mode for temporal filtering."""
    
    RECENT = "recent"
    HISTORICAL = "historical"
    RANGE = "range"


class TemporalHint(BaseModel):
    """Temporal filtering configuration."""
    
    mode: TemporalMode = Field(..., description="Temporal filter mode")
    days_back: int | None = Field(None, description="For 'recent' mode: number of days back")
    start_date: date | None = Field(None, description="For 'range' mode: start date")
    end_date: date | None = Field(None, description="For 'range' mode: end date")


class TypePriority(BaseModel):
    """Priority configuration for artifact type."""
    
    type: str = Field(..., description="Artifact type")
    priority: int = Field(..., ge=1, description="Priority (1=highest)")


class ContextPreferences(BaseModel):
    """Preferences for context assembly."""
    
    artifact_types: list[TypePriority] | None = Field(
        None, description="Prioritize certain artifact types"
    )
    source_systems: list[str] | None = Field(
        None, description="Prefer artifacts from certain source systems"
    )
    min_confidence: float | None = Field(
        None, ge=0.0, le=1.0, description="Minimum relation confidence threshold"
    )
    prefer_recent: bool | None = Field(None, description="Apply recency bias to scoring")


class ContextHints(BaseModel):
    """Optional hints to influence context assembly.
    
    These hints enable "smart" context generation tailored to specific use cases.
    All fields are optional - when not provided, defaults are used.
    """
    
    query: str | None = Field(
        None, description="The prompt/question driving this request (enables relevance scoring)"
    )
    task_type: str | None = Field(
        None, description="Intent: qa, summarization, analysis, comparison"
    )
    token_budget: int | None = Field(
        None, gt=0, description="Max tokens for context (forces prioritization)"
    )
    temporal_focus: TemporalHint | None = Field(
        None, description="Filter by artifact creation date"
    )
    relevance_threshold: float | None = Field(
        None, ge=0.0, le=1.0, description="Filter by semantic relevance to query"
    )
    exclusions: list[UUID] | None = Field(
        None, description="Artifacts to explicitly exclude from context"
    )
    preferences: ContextPreferences | None = Field(
        None, description="Assembly preferences"
    )


# ============================================================================
# Response Models
# ============================================================================

class ContextHintsApplied(BaseModel):
    """Summary of how hints affected context results."""
    
    query_provided: bool = Field(False, description="Whether query hint was provided")
    token_budget_enforced: bool = Field(False, description="Whether token budget was applied")
    temporal_filter_applied: bool = Field(False, description="Whether temporal filter was applied")
    relevance_filtering_applied: bool = Field(False, description="Whether relevance threshold was used")
    exclusions_applied: int = Field(0, description="Number of artifacts excluded by hint")


class ContextMetadata(BaseModel):
    """Metadata about the context retrieval operation."""
    
    depth_used: int = Field(..., description="Actual traversal depth used")
    artifact_count: int = Field(..., description="Total artifacts in context (excluding primary)")
    tokens_estimated: int | None = Field(None, description="Estimated token count if budget was set")
    artifacts_excluded: int = Field(0, description="Count of artifacts filtered out")


class ContextResponse(BaseModel):
    """Response containing primary artifact and its context.
    
    The context is assembled according to the specified policy and hints.
    """
    
    artifact: ArtifactResponse = Field(..., description="The primary/requested artifact")
    context: list[ContextArtifact] = Field(
        default_factory=list,
        description="Related artifacts with relationship metadata"
    )
    policy: ContextPolicy = Field(..., description="Policy that was applied")
    hints_applied: ContextHintsApplied = Field(
        default_factory=ContextHintsApplied,
        description="Summary of how hints affected results"
    )
    metadata: ContextMetadata = Field(..., description="Operation metadata")