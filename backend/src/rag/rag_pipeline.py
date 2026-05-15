"""Simple RAG pipeline that ties all components together."""

from __future__ import annotations

import logging
from typing import Optional

from backend.src.rag.retriever import get_retriever, RetrievedChunk
from backend.src.rag.generator import get_generator, GeneratedResponse
from backend.src.rag.uncertainty import get_uncertainty_estimator, UncertaintyEstimate
from backend.src.rag.calibration import get_calibration_manager

logger = logging.getLogger(__name__)


def process_query(
    query: str,
    atm_id: Optional[str] = None,
    top_k: int = 5,
    include_uncertainty: bool = True,
) -> dict:
    """Process a RAG query through the full pipeline."""
    try:
        retriever = get_retriever()
        generator = get_generator()
        uncertainty_estimator = get_uncertainty_estimator()
        calibration_manager = get_calibration_manager()

        chunks = retriever.retrieve(query=query, atm_id=atm_id, top_k=top_k)

        if not chunks:
            return {
                "error": "No relevant logs found",
                "answer": "I couldn't find any relevant log data for your query.",
            }

        response = generator.generate(query=query, chunks=chunks)

        uncertainty = None
        if include_uncertainty:
            uncertainty = uncertainty_estimator.estimate(query=query, chunks=chunks)

            if calibration_manager.params.is_fitted:
                calibrated = calibration_manager.apply(uncertainty.final_confidence)
                uncertainty.final_confidence = calibrated.calibrated_confidence

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
            "confidence_level": uncertainty.confidence_level if uncertainty else "medium",
            "is_uncertain": uncertainty.is_uncertain if uncertainty else False,
            "recommendation": uncertainty.recommendation if uncertainty else "Review recommended",
            "model_used": response.model,
        }

    except Exception as e:
        logger.error(f"RAG pipeline failed: {e}")
        return {
            "error": str(e),
            "answer": "I encountered an error processing your request.",
        }