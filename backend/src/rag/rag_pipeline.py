"""Simple RAG pipeline that ties all components together with Agentic RAG."""

from __future__ import annotations

import logging
from typing import Optional

from backend.src.rag.retriever import get_retriever
from backend.src.rag.generator import get_generator
from backend.src.rag.uncertainty import get_uncertainty_estimator

logger = logging.getLogger(__name__)


def process_query(
    query: str,
    atm_id: Optional[str] = None,
    top_k: int = 3,
    include_uncertainty: bool = True,
    enable_reflexion: Optional[bool] = None,
    enable_citation_grounding: Optional[bool] = None,
    enable_self_consistency: Optional[bool] = None,
) -> dict:
    """Process a RAG query through the full Agentic RAG pipeline.

    Args:
        query: User query
        atm_id: Optional ATM ID filter
        top_k: Number of chunks to retrieve
        include_uncertainty: Whether to include uncertainty estimation
        enable_reflexion: Enable self-critique and regeneration
        enable_citation_grounding: Enable citation verification
        enable_self_consistency: Enable multi-sample consistency scoring
    """
    try:
        retriever = get_retriever()
        generator = get_generator()
        uncertainty_estimator = get_uncertainty_estimator()

        chunks = retriever.retrieve(query=query, atm_id=atm_id, top_k=top_k)

        if not chunks:
            return {
                "error": "No relevant logs found",
                "answer": "I couldn't find any relevant log data for your query.",
            }

        response = generator.generate(
            query=query,
            chunks=chunks,
            enable_reflexion=enable_reflexion,
            enable_citation_grounding=enable_citation_grounding,
            enable_self_consistency=enable_self_consistency,
        )

        uncertainty = None
        if include_uncertainty:
            uncertainty = uncertainty_estimator.estimate(
                query=query,
                chunks=chunks,
                self_consistency_score=response.self_consistency_score,
                verbalized_confidence=response.verbalized_confidence,
                grounding_score=response.grounding_score,
            )

        return {
            "answer": response.text,
            "sources": [
                {
                    "text": c.text,
                    "chunk_id": c.chunk_id,
                    "atm_id": c.atm_id,
                    "timestamp": c.timestamp,
                    "confidence_score": c.confidence_score,
                }
                for c in response.sources
            ],
            "uncertainty_score": uncertainty.final_confidence if uncertainty else 0.5,
            "confidence_level": uncertainty.confidence_level
            if uncertainty
            else "medium",
            "is_uncertain": uncertainty.is_uncertain if uncertainty else False,
            "recommendation": uncertainty.recommendation
            if uncertainty
            else "Review recommended",
            "model_used": response.model,
            "self_consistency_score": response.self_consistency_score,
            "verbalized_confidence": response.verbalized_confidence,
            "grounding_score": response.grounding_score,
            "generation_variance": uncertainty.generation_variance
            if uncertainty
            else None,
            "cross_encoder_used": response.cross_encoder_used,
            "was_revised": response.was_revised,
        }

    except Exception as e:
        logger.error(f"RAG pipeline failed: {e}")
        return {
            "error": str(e),
            "answer": "I encountered an error processing your request.",
        }
