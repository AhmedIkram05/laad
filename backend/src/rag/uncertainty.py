"""Uncertainty estimation using self-consistency and verbalized confidence."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Optional

from backend.src.rag.llm_client import get_llm_client, LLMResponse
from backend.src.rag.retriever import RetrievedChunk
from backend.src.rag.generator import get_generator, SYSTEM_PROMPT

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
    """Estimates uncertainty using hybrid approach: self-consistency + verbalized confidence."""

    def __init__(self):
        self.llm_client = get_llm_client()
        self.generator = get_generator()
        self.num_samples = 1

    def estimate(
        self,
        query: str,
        chunks: list[RetrievedChunk],
    ) -> UncertaintyEstimate:
        """Estimate uncertainty for a query with retrieved context."""
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

        avg_distance = sum(c.distance for c in chunks) / len(chunks)
        retrieval_confidence = max(0.0, 1.0 - min(avg_distance, 1.0))

        try:
            responses = self._self_consistency_sample(query, chunks)
        except Exception:
            responses = []

        if not responses:
            return UncertaintyEstimate(
                final_confidence=round(retrieval_confidence, 3),
                confidence_level=self._classify_confidence(retrieval_confidence),
                self_consistency_score=0.0,
                verbalized_confidence=None,
                generation_variance=None,
                is_uncertain=retrieval_confidence < 0.5,
                recommendation=self._get_recommendation(retrieval_confidence, self._classify_confidence(retrieval_confidence)),
            )

        consistency_score = self._calculate_consistency(responses)

        verbal_conf = self._extract_verbalized_confidence(responses[0].text)

        variance = self._calculate_variance(responses)

        final_conf = self._combine_signals(
            consistency_score=consistency_score,
            verbal_confidence=verbal_conf,
            variance=variance,
        )

        confidence_level = self._classify_confidence(final_conf)

        is_uncertain = final_conf < 0.5

        recommendation = self._get_recommendation(final_conf, confidence_level)

        logger.info(
            f"Uncertainty estimate: confidence={final_conf:.2f}, "
            f"consistency={consistency_score:.2f}, verbal={verbal_conf}, "
            f"level={confidence_level}"
        )

        return UncertaintyEstimate(
            final_confidence=round(final_conf, 3),
            confidence_level=confidence_level,
            self_consistency_score=round(consistency_score, 3),
            verbalized_confidence=verbal_conf,
            generation_variance=round(variance, 3) if variance else None,
            is_uncertain=is_uncertain,
            recommendation=recommendation,
        )

    def _self_consistency_sample(
        self,
        query: str,
        chunks: list[RetrievedChunk],
    ) -> list[LLMResponse]:
        """Generate multiple responses to measure self-consistency."""
        responses = []
        context = self._build_context(chunks)
        prompt = self._build_prompt_with_confidence_request(query, context)

        for i in range(self.num_samples):
            try:
                response = self.llm_client.generate(
                    prompt=prompt,
                    system_prompt=SYSTEM_PROMPT,
                    temperature=0.6,
                )
                responses.append(response)
            except Exception as e:
                logger.warning(f"Sample {i+1} failed: {e}")
                continue

        return responses

    def _build_context(self, chunks: list[RetrievedChunk]) -> str:
        """Build context from chunks."""
        return "\n".join([f"[Log {i+1}]: {c.text}" for i, c in enumerate(chunks)])

    def _build_prompt_with_confidence_request(self, query: str, context: str) -> str:
        """Build prompt that asks for confidence rating."""
        return f"""Based on the following ATM log data, answer the question and provide a confidence rating.

Context:
{context}

Question: {query}

Please provide your answer and end your response with a confidence rating in this format:
CONFIDENCE: [number between 0 and 1, where 1 is completely certain]

Example: ... Your detailed answer here. CONFIDENCE: 0.85"""

    def _calculate_consistency(self, responses: list[LLMResponse]) -> float:
        """Calculate semantic consistency between responses."""
        if len(responses) < 2:
            return 1.0

        texts = [r.text.lower()[:200] for r in responses]

        consistency_scores = []
        for i in range(len(texts)):
            for j in range(i + 1, len(texts)):
                score = self._text_similarity(texts[i], texts[j])
                consistency_scores.append(score)

        return sum(consistency_scores) / len(consistency_scores) if consistency_scores else 0.5

    def _text_similarity(self, text1: str, text2: str) -> float:
        """Calculate simple word overlap similarity."""
        words1 = set(text1.split())
        words2 = set(text2.split())

        if not words1 or not words2:
            return 0.0

        intersection = words1.intersection(words2)
        union = words1.union(words2)

        return len(intersection) / len(union)

    def _extract_verbalized_confidence(self, text: str) -> Optional[float]:
        """Extract confidence rating from response text."""
        match = re.search(r'CONFIDENCE:\s*([0-9]*\.?[0-9]+)', text, re.IGNORECASE)
        if match:
            try:
                conf = float(match.group(1))
                return max(0.0, min(1.0, conf))
            except ValueError:
                pass
        return None

    def _calculate_variance(self, responses: list[LLMResponse]) -> float:
        """Calculate variance in response lengths as proxy for instability."""
        if not responses:
            return 0.0

        lengths = [len(r.text) for r in responses]
        if len(lengths) < 2:
            return 0.0

        mean_len = sum(lengths) / len(lengths)
        variance = sum((l - mean_len) ** 2 for l in lengths) / len(lengths)

        normalized_variance = min(variance / (mean_len ** 2 + 1), 1.0)
        return normalized_variance

    def _combine_signals(
        self,
        consistency_score: float,
        verbal_confidence: Optional[float],
        variance: float,
    ) -> float:
        """Combine multiple uncertainty signals into final confidence."""
        signals = [consistency_score]

        if verbal_confidence is not None:
            signals.append(verbal_confidence)

        variance_signal = max(0, 1 - variance * 2)
        signals.append(variance_signal)

        weights = [0.5, 0.3, 0.2][:len(signals)]
        total_weight = sum(weights)

        combined = sum(s * w for s, w in zip(signals, weights)) / total_weight
        return combined

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


_estimator: Optional[UncertaintyEstimator] = None


def get_uncertainty_estimator() -> UncertaintyEstimator:
    """Get singleton uncertainty estimator instance."""
    global _estimator
    if _estimator is None:
        _estimator = UncertaintyEstimator()
    return _estimator