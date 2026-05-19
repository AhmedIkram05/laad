"""Uncertainty estimation using retrieval-based confidence only."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from backend.src.rag.retriever import RetrievedChunk

logger = logging.getLogger(__name__)


@dataclass
class UncertaintyEstimate:
    """Uncertainty estimate with multiple signals."""
    final_confidence: float
    confidence_level: str
    self_consistency_score: float
    verbalized_confidence: Optional[float]
    generation_variance: Optional[float]
    is_uncertain: bool
    recommendation: str


class UncertaintyEstimator:
    """Estimates uncertainty using retrieval-based confidence only."""

    def __init__(self):
        pass

    def estimate(
        self,
        query: str,
        chunks: list[RetrievedChunk],
    ) -> UncertaintyEstimate:
        """Estimate confidence based purely on retrieval quality."""
        if not chunks:
            return UncertaintyEstimate(
                final_confidence=0.0,
                confidence_level="low",
                self_consistency_score=0.0,
                verbalized_confidence=None,
                generation_variance=None,
                is_uncertain=True,
                recommendation="Insufficient context - escalate to human review",
            )

        retrieval_confidence = compute_retrieval_confidence(chunks)

        confidence_level = self._classify_confidence(retrieval_confidence)
        is_uncertain = retrieval_confidence < 0.5
        recommendation = self._get_recommendation(retrieval_confidence, confidence_level)

        logger.info(
            f"Uncertainty estimate: confidence={retrieval_confidence:.2f}, "
            f"level={confidence_level}"
        )

        return UncertaintyEstimate(
            final_confidence=round(retrieval_confidence, 3),
            confidence_level=confidence_level,
            self_consistency_score=round(retrieval_confidence, 3),
            verbalized_confidence=None,
            generation_variance=None,
            is_uncertain=is_uncertain,
            recommendation=recommendation,
        )

    def _classify_confidence(self, confidence: float) -> str:
        """Classify confidence into level."""
        if confidence >= 0.8:
            return "high"
        elif confidence >= 0.5:
            return "medium"
        else:
            return "low"

    def _get_recommendation(self, confidence: float, level: str) -> str:
        """Get recommendation based on confidence level."""
        if level == "high":
            return "Auto-respond - high confidence in answer quality"
        elif level == "medium":
            return "Verify - moderate confidence, review before presenting"
        else:
            return "Escalate - low confidence, route to human expert"


def compute_retrieval_confidence(chunks: list[RetrievedChunk]) -> float:
    """Compute confidence score from retrieval quality signals.
    
    Combines:
    - Distance score: 1.0 - avg_distance (base signal)
    - Count bonus: more relevant chunks = higher confidence (up to +0.1)
    - Diversity bonus: multiple ATMs involved = higher confidence (up to +0.1)
    """
    if not chunks:
        return 0.0

    avg_distance = sum(c.distance for c in chunks) / len(chunks)
    distance_score = max(0.0, 1.0 - avg_distance)

    count_bonus = min(len(chunks) / 5, 0.1)

    sources = set(c.atm_id for c in chunks if c.atm_id)
    diversity_bonus = min(len(sources) - 1, 0.1) if sources else 0.0

    return min(1.0, distance_score + count_bonus + diversity_bonus)


_estimator: Optional[UncertaintyEstimator] = None


def get_uncertainty_estimator() -> UncertaintyEstimator:
    """Get singleton uncertainty estimator instance."""
    global _estimator
    if _estimator is None:
        _estimator = UncertaintyEstimator()
    return _estimator
