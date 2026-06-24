"""Pydantic schemas for RAG API with Agentic RAG fields."""

from __future__ import annotations
from typing import Literal, Optional
from pydantic import BaseModel, Field


class RAGQueryRequest(BaseModel):
    """Request body for RAG query."""

    query: str = Field(..., min_length=1, max_length=1000, description="User query")
    atm_id: Optional[str] = Field(None, description="Filter by specific ATM ID")
    top_k: int = Field(10, ge=1, le=20, description="Number of chunks to retrieve")
    include_uncertainty: bool = Field(
        True, description="Include uncertainty estimation"
    )
    error_only: Optional[bool] = Field(
        None, description="Filter for ERROR/FATAL severity only"
    )
    most_recent_first: Optional[bool] = Field(
        None, description="Sort by timestamp descending"
    )
    enable_reflexion: Optional[bool] = Field(
        None, description="Enable self-critique and regeneration"
    )
    enable_citation_grounding: Optional[bool] = Field(
        None, description="Enable entity citation verification"
    )
    enable_self_consistency: Optional[bool] = Field(
        None, description="Enable multi-sample consistency scoring"
    )


class SourceChunk(BaseModel):
    """Retrieved source chunk."""

    text: str
    chunk_id: str
    atm_id: Optional[str]
    timestamp: Optional[str]
    confidence_score: float


class RAGQueryResponse(BaseModel):
    """Response for RAG query with agentic metadata."""

    query_id: Optional[int] = None
    answer: str
    sources: list[SourceChunk]
    uncertainty_score: float
    confidence_level: str
    is_uncertain: bool
    recommendation: str
    model_used: str

    self_consistency_score: Optional[float] = Field(
        None, description="Consistency across multiple samples (0-1)"
    )
    verbalized_confidence: Optional[float] = Field(
        None, description="LLM's self-rated confidence (0-1)"
    )
    grounding_score: Optional[float] = Field(
        None, description="Fraction of cited entities verified in sources (0-1)"
    )
    generation_variance: Optional[float] = Field(
        None, description="1 - self_consistency_score"
    )
    cross_encoder_used: bool = Field(
        False, description="Whether cross-encoder reranking was applied"
    )
    was_revised: bool = Field(
        False, description="Whether reflexion triggered a revision"
    )
    critique_text: Optional[str] = Field(None, description="Reflexion critique output")


class RAGFeedbackRequest(BaseModel):
    """Request body for RAG feedback."""

    query_id: int = Field(..., description="Query ID to provide feedback on")
    feedback: Literal["helpful", "not_helpful", "uncertain"] = Field(
        ..., description="Feedback type"
    )


class RAGFeedbackResponse(BaseModel):
    """Response for RAG feedback."""

    success: bool
    message: str


class RAGHistoryItem(BaseModel):
    """Single history item."""

    id: int
    query_text: str
    answer_text: str
    uncertainty_score: float
    created_at: str


class RAGHistoryResponse(BaseModel):
    """Response for history query."""

    history: list[RAGHistoryItem]
    total: int


class RAGStatsResponse(BaseModel):
    """RAG system statistics."""

    collection_chunks: int
    total_queries: int


class AnomalyStatsResponse(BaseModel):
    """Response for anomaly statistics queries."""

    total: int
    by_type: dict[str, int] = Field(default_factory=dict)
    by_atm: dict[str, int] = Field(default_factory=dict)
    by_severity: dict[str, int] = Field(default_factory=dict)
    active: int = 0
    resolved: int = 0
