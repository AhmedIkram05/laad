"""Uncertainty estimation using multi-signal confidence fusion.

Combines retrieval-based confidence, self-consistency, LLM verbalized confidence,
and citation grounding into a unified uncertainty score. Each signal is weighted
to produce a robust final confidence estimate.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from backend.src.rag.retriever import RetrievedChunk

logger = logging.getLogger(__name__)

# Default fusion weights — sum to 1.0
W_RETRIEVAL = 0.30
W_CONSISTENCY = 0.25
W_VERBALIZED = 0.25
W_GROUNDING = 0.20


@dataclass
class UncertaintyEstimate:
    """Uncertainty estimate with multiple signals fused."""
    final_confidence: float
    confidence_level: str
    self_consistency_score: Optional[float] = None
    verbalized_confidence: Optional[float] = None
    generation_variance: Optional[float] = None
    grounding_score: Optional[float] = None
    is_uncertain: bool = True
    recommendation: str = "Insufficient information"


class UncertaintyEstimator:
    """Estimates uncertainty by fusing multiple confidence signals.

    Fuses retrieval quality, self-consistency, LLM verbalized confidence,
    and citation grounding into a single calibrated confidence score.
    """

    def __init__(self):
        pass

    def estimate(
        self,
        query: str,
        chunks: list[RetrievedChunk],
        self_consistency_score: Optional[float] = None,
        verbalized_confidence: Optional[float] = None,
        grounding_score: Optional[float] = None,
    ) -> UncertaintyEstimate:
        """Estimate confidence by fusing multiple signals.

        Args:
            query: User query (unused, kept for API compatibility)
            chunks: Retrieved chunks for retrieval-based confidence
            self_consistency_score: From multi-sample generation
            verbalized_confidence: LLM's self-rated confidence
            grounding_score: Entity citation verification score
        """
        if not chunks:
            return UncertaintyEstimate(
                final_confidence=0.0,
                confidence_level="low",
                self_consistency_score=self_consistency_score,
                verbalized_confidence=verbalized_confidence,
                grounding_score=grounding_score,
                is_uncertain=True,
                recommendation="Insufficient context - escalate to human review",
            )

        retrieval_confidence = compute_retrieval_confidence(chunks)

        return self._fuse_signals(
            retrieval_confidence=retrieval_confidence,
            self_consistency_score=self_consistency_score,
            verbalized_confidence=verbalized_confidence,
            grounding_score=grounding_score,
        )

    def _fuse_signals(
        self,
        retrieval_confidence: float,
        self_consistency_score: Optional[float] = None,
        verbalized_confidence: Optional[float] = None,
        grounding_score: Optional[float] = None,
    ) -> UncertaintyEstimate:
        """Fuse multiple confidence signals into a single score.

        Uses weighted average with configurable weights. Missing signals are
        skipped and remaining weights are renormalized.
        """
        signals: list[tuple[float, float]] = [
            (retrieval_confidence, W_RETRIEVAL),
        ]

        if self_consistency_score is not None:
            signals.append((self_consistency_score, W_CONSISTENCY))
        if verbalized_confidence is not None:
            signals.append((verbalized_confidence, W_VERBALIZED))
        if grounding_score is not None:
            signals.append((grounding_score, W_GROUNDING))

        total_weight = sum(w for _, w in signals)
        if total_weight == 0:
            fused = retrieval_confidence
        else:
            normalized_signals = [(s * w / total_weight) for s, w in signals]
            fused = sum(normalized_signals)

        final_confidence = round(max(0.0, min(1.0, fused)), 3)
        confidence_level = self._classify_confidence(final_confidence)
        is_uncertain = final_confidence < 0.5
        recommendation = self._get_recommendation(final_confidence, confidence_level)

        logger.info(
            f"Fused confidence: {final_confidence:.3f} (level={confidence_level}) "
            f"signals: retrieval={retrieval_confidence:.3f}, "
            f"consistency={self_consistency_score}, "
            f"verbalized={verbalized_confidence}, "
            f"grounding={grounding_score}"
        )

        return UncertaintyEstimate(
            final_confidence=final_confidence,
            confidence_level=confidence_level,
            self_consistency_score=round(self_consistency_score, 3) if self_consistency_score is not None else None,
            verbalized_confidence=round(verbalized_confidence, 3) if verbalized_confidence is not None else None,
            generation_variance=1.0 - round(self_consistency_score, 3) if self_consistency_score is not None else None,
            grounding_score=round(grounding_score, 3) if grounding_score is not None else None,
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
        """Get recommendation based on confidence level and available signals."""
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
