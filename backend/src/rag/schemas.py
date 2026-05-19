"""Pydantic schemas for RAG API."""

from __future__ import annotations
from typing import Literal, Optional
from pydantic import BaseModel, Field


class RAGQueryRequest(BaseModel):
    """Request body for RAG query."""
    query: str = Field(..., min_length=1, max_length=1000, description="User query")
    atm_id: Optional[str] = Field(None, description="Filter by specific ATM ID")
    top_k: int = Field(3, ge=1, le=20, description="Number of chunks to retrieve")
    include_uncertainty: bool = Field(True, description="Include uncertainty estimation")


class SourceChunk(BaseModel):
    """Retrieved source chunk."""
    text: str
    chunk_id: str
    atm_id: Optional[str]
    timestamp: Optional[str]
    confidence_score: float


class RAGQueryResponse(BaseModel):
    """Response for RAG query."""
    query_id: Optional[int] = None
    answer: str
    sources: list[SourceChunk]
    uncertainty_score: float
    confidence_level: str
    is_uncertain: bool
    recommendation: str
    model_used: str


class RAGFeedbackRequest(BaseModel):
    """Request body for RAG feedback."""
    query_id: int = Field(..., description="Query ID to provide feedback on")
    feedback: Literal["helpful", "not_helpful", "uncertain"] = Field(..., description="Feedback type")


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