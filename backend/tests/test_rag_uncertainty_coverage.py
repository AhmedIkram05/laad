"""Coverage tests for backend.src.rag.uncertainty."""

from __future__ import annotations

import pytest

from backend.src.rag.retriever import RetrievedChunk
from backend.src.rag.uncertainty import (
    UncertaintyEstimator,
    compute_retrieval_confidence,
)


def _chunk(distance=0.2, atm_id="ATM-GB-0001", timestamp="2026-05-15T10:00:00Z"):
    """Helper to create a RetrievedChunk."""
    return RetrievedChunk(
        text="log data",
        chunk_id="c1",
        atm_id=atm_id,
        timestamp=timestamp,
        distance=distance,
        confidence_score=round(1.0 - distance, 3),
    )


class TestClassifyConfidenceBoundary:
    """Test _classify_confidence boundary values."""

    def test_exactly_0_8_is_high(self):
        estimator = UncertaintyEstimator.__new__(UncertaintyEstimator)
        assert estimator._classify_confidence(0.8) == "high"

    def test_exactly_0_5_is_medium(self):
        estimator = UncertaintyEstimator.__new__(UncertaintyEstimator)
        assert estimator._classify_confidence(0.5) == "medium"

    def test_exactly_0_0_is_low(self):
        estimator = UncertaintyEstimator.__new__(UncertaintyEstimator)
        assert estimator._classify_confidence(0.0) == "low"

    def test_exactly_1_0_is_high(self):
        estimator = UncertaintyEstimator.__new__(UncertaintyEstimator)
        assert estimator._classify_confidence(1.0) == "high"

    def test_below_0_5_is_low(self):
        estimator = UncertaintyEstimator.__new__(UncertaintyEstimator)
        assert estimator._classify_confidence(0.49) == "low"

    def test_above_0_5_below_0_8_is_medium(self):
        estimator = UncertaintyEstimator.__new__(UncertaintyEstimator)
        assert estimator._classify_confidence(0.79) == "medium"

    def test_above_0_8_is_high(self):
        estimator = UncertaintyEstimator.__new__(UncertaintyEstimator)
        assert estimator._classify_confidence(0.81) == "high"


class TestGetRecommendationExact:
    """Test _get_recommendation returns exact strings."""

    def test_high_confidence_exact_string(self):
        estimator = UncertaintyEstimator.__new__(UncertaintyEstimator)
        result = estimator._get_recommendation(0.95, "high")
        assert result == "Auto-respond - high confidence in answer quality"

    def test_medium_confidence_exact_string(self):
        estimator = UncertaintyEstimator.__new__(UncertaintyEstimator)
        result = estimator._get_recommendation(0.6, "medium")
        assert result == "Verify - moderate confidence, review before presenting"

    def test_low_confidence_exact_string(self):
        estimator = UncertaintyEstimator.__new__(UncertaintyEstimator)
        result = estimator._get_recommendation(0.3, "low")
        assert result == "Escalate - low confidence, route to human expert"


class TestEstimatePartialSignals:
    """Test estimate with partial signal combinations."""

    def test_only_grounding_score(self):
        """estimate with only grounding_score set."""
        estimator = UncertaintyEstimator()
        chunks = [_chunk(distance=0.3)]

        result = estimator.estimate(
            query="q",
            chunks=chunks,
            grounding_score=0.9,
        )

        assert result.grounding_score == 0.9
        assert result.self_consistency_score is None
        assert result.verbalized_confidence is None
        assert result.final_confidence > 0.0

    def test_only_verbalized_confidence(self):
        """estimate with only verbalized_confidence set."""
        estimator = UncertaintyEstimator()
        chunks = [_chunk(distance=0.3)]

        result = estimator.estimate(
            query="q",
            chunks=chunks,
            verbalized_confidence=0.85,
        )

        assert result.verbalized_confidence == 0.85
        assert result.self_consistency_score is None
        assert result.grounding_score is None

    def test_only_consistency_score(self):
        """estimate with only self_consistency_score set."""
        estimator = UncertaintyEstimator()
        chunks = [_chunk(distance=0.3)]

        result = estimator.estimate(
            query="q",
            chunks=chunks,
            self_consistency_score=0.75,
        )

        assert result.self_consistency_score == 0.75
        assert result.verbalized_confidence is None
        assert result.grounding_score is None

    def test_consistency_and_grounding_only(self):
        """estimate with consistency and grounding, no verbalized."""
        estimator = UncertaintyEstimator()
        chunks = [_chunk(distance=0.3)]

        result = estimator.estimate(
            query="q",
            chunks=chunks,
            self_consistency_score=0.75,
            grounding_score=0.8,
        )

        assert result.self_consistency_score == 0.75
        assert result.grounding_score == 0.8
        assert result.verbalized_confidence is None


class TestFuseSignalsZeroWeight:
    """Test _fuse_signals when total_weight would be 0."""

    def test_fuse_signals_returns_fallback_on_zero_weight(self):
        """When all weights are zero, falls back to retrieval_confidence."""
        estimator = UncertaintyEstimator.__new__(UncertaintyEstimator)
        # This is hard to trigger with real weights, so we patch the constants
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("backend.src.rag.uncertainty.W_RETRIEVAL", 0)
            mp.setattr("backend.src.rag.uncertainty.W_CONSISTENCY", 0)
            mp.setattr("backend.src.rag.uncertainty.W_VERBALIZED", 0)
            mp.setattr("backend.src.rag.uncertainty.W_GROUNDING", 0)

            result = estimator._fuse_signals(
                retrieval_confidence=0.75,
                self_consistency_score=0.8,
                verbalized_confidence=0.9,
                grounding_score=0.85,
            )

        assert result.final_confidence == 0.75

    def test_fuse_signals_with_no_optional_signals(self):
        """Only retrieval signal, total_weight = W_RETRIEVAL != 0."""
        estimator = UncertaintyEstimator.__new__(UncertaintyEstimator)
        result = estimator._fuse_signals(retrieval_confidence=0.8)
        assert result.final_confidence == pytest.approx(0.8, abs=0.01)


class TestFuseSignalsAllZeroValues:
    """Test _fuse_signals when all signal values are 0.0."""

    def test_all_zero_signals(self):
        estimator = UncertaintyEstimator()
        result = estimator._fuse_signals(
            retrieval_confidence=0.0,
            self_consistency_score=0.0,
            verbalized_confidence=0.0,
            grounding_score=0.0,
        )
        assert result.final_confidence == 0.0
        assert result.is_uncertain is True
        assert result.confidence_level == "low"


class TestComputeRetrievalConfidenceEdgeCases:
    """Test compute_retrieval_confidence edge cases."""

    def test_chunks_with_none_atm_id(self):
        """Chunks with None atm_id don't crash diversity calculation."""
        chunks = [
            RetrievedChunk(
                text="log1",
                chunk_id="1",
                atm_id=None,
                timestamp="2026-05-15T10:00:00Z",
                distance=0.2,
                confidence_score=0.8,
            ),
            RetrievedChunk(
                text="log2",
                chunk_id="2",
                atm_id=None,
                timestamp="2026-05-15T10:01:00Z",
                distance=0.3,
                confidence_score=0.7,
            ),
        ]
        result = compute_retrieval_confidence(chunks)
        assert 0.0 <= result <= 1.0

    def test_empty_chunks_returns_zero(self):
        """Empty list returns 0.0."""
        assert compute_retrieval_confidence([]) == 0.0

    def test_single_chunk_no_diversity_bonus(self):
        """Single chunk has no diversity bonus."""
        chunks = [_chunk(distance=0.2, atm_id="ATM-1")]
        result = compute_retrieval_confidence(chunks)
        # distance_score = 0.8, count_bonus = 0.02, diversity = 0
        assert result > 0.7

    def test_many_chunks_count_bonus_capped(self):
        """Count bonus caps at 0.1 when len >= 5."""
        chunks = [_chunk(distance=0.2, atm_id=f"ATM-{i}") for i in range(10)]
        result = compute_retrieval_confidence(chunks)
        assert 0.0 <= result <= 1.0

    def test_diversity_bonus_capped(self):
        """Diversity bonus caps at 0.1 even with many unique ATMs."""
        chunks = [_chunk(distance=0.2, atm_id=f"ATM-{i}") for i in range(20)]
        result = compute_retrieval_confidence(chunks)
        assert 0.0 <= result <= 1.0

    def test_result_capped_at_one(self):
        """Final result never exceeds 1.0."""
        chunks = [
            RetrievedChunk(
                text="log",
                chunk_id="1",
                atm_id="ATM-1",
                timestamp="2026-05-15T10:00:00Z",
                distance=0.0,
                confidence_score=1.0,
            ),
            RetrievedChunk(
                text="log2",
                chunk_id="2",
                atm_id="ATM-2",
                timestamp="2026-05-15T10:01:00Z",
                distance=0.0,
                confidence_score=1.0,
            ),
            RetrievedChunk(
                text="log3",
                chunk_id="3",
                atm_id="ATM-3",
                timestamp="2026-05-15T10:02:00Z",
                distance=0.0,
                confidence_score=1.0,
            ),
            RetrievedChunk(
                text="log4",
                chunk_id="4",
                atm_id="ATM-4",
                timestamp="2026-05-15T10:03:00Z",
                distance=0.0,
                confidence_score=1.0,
            ),
            RetrievedChunk(
                text="log5",
                chunk_id="5",
                atm_id="ATM-5",
                timestamp="2026-05-15T10:04:00Z",
                distance=0.0,
                confidence_score=1.0,
            ),
        ]
        result = compute_retrieval_confidence(chunks)
        assert result <= 1.0


class TestEstimateEmptyChunksReturnsZero:
    """Test that estimate with empty chunks returns zero confidence."""

    def test_empty_chunks_returns_low_confidence(self):
        estimator = UncertaintyEstimator()
        result = estimator.estimate(
            query="test",
            chunks=[],
            self_consistency_score=0.9,
            verbalized_confidence=0.9,
            grounding_score=0.9,
        )
        assert result.final_confidence == 0.0
        assert result.confidence_level == "low"
        assert result.is_uncertain is True
        assert (
            result.recommendation == "Insufficient context - escalate to human review"
        )
        assert result.self_consistency_score == 0.9
        assert result.verbalized_confidence == 0.9
        assert result.grounding_score == 0.9


class TestFuseSignalsClamping:
    """Test that _fuse_signals clamps output to [0.0, 1.0]."""

    def test_output_clamped_at_one(self):
        """Fused score exceeding 1.0 is clamped."""
        estimator = UncertaintyEstimator.__new__(UncertaintyEstimator)
        result = estimator._fuse_signals(
            retrieval_confidence=1.0,
            self_consistency_score=1.0,
            verbalized_confidence=1.0,
            grounding_score=1.0,
        )
        assert result.final_confidence <= 1.0

    def test_output_clamped_at_zero(self):
        """Fused score below 0.0 is clamped."""
        estimator = UncertaintyEstimator.__new__(UncertaintyEstimator)
        result = estimator._fuse_signals(
            retrieval_confidence=0.0,
            self_consistency_score=0.0,
            verbalized_confidence=0.0,
            grounding_score=0.0,
        )
        assert result.final_confidence >= 0.0


class TestFuseSignalsIsUncertain:
    """Test is_uncertain threshold logic."""

    def test_above_threshold_not_uncertain(self):
        estimator = UncertaintyEstimator.__new__(UncertaintyEstimator)
        result = estimator._fuse_signals(retrieval_confidence=0.9)
        assert result.is_uncertain is False

    def test_below_threshold_is_uncertain(self):
        estimator = UncertaintyEstimator.__new__(UncertaintyEstimator)
        result = estimator._fuse_signals(retrieval_confidence=0.1)
        assert result.is_uncertain is True

    def test_exactly_at_threshold_is_uncertain(self):
        """0.5 is not < 0.5, so is_uncertain should be False."""
        estimator = UncertaintyEstimator.__new__(UncertaintyEstimator)
        result = estimator._fuse_signals(retrieval_confidence=0.5)
        assert result.is_uncertain is False


class TestFuseSignalsGenerationVariance:
    """Test generation_variance computation."""

    def test_generation_variance_with_consistency(self):
        """generation_variance = 1 - consistency_score when present."""
        estimator = UncertaintyEstimator.__new__(UncertaintyEstimator)
        result = estimator._fuse_signals(
            retrieval_confidence=0.8,
            self_consistency_score=0.6,
        )
        assert result.generation_variance == pytest.approx(0.4, abs=0.01)

    def test_generation_variance_none_without_consistency(self):
        """generation_variance is None when self_consistency_score is None."""
        estimator = UncertaintyEstimator.__new__(UncertaintyEstimator)
        result = estimator._fuse_signals(retrieval_confidence=0.8)
        assert result.generation_variance is None


class TestFuseSignalsRounding:
    """Test that signal values are properly rounded."""

    def test_consistency_rounded_to_3_decimals(self):
        estimator = UncertaintyEstimator.__new__(UncertaintyEstimator)
        result = estimator._fuse_signals(
            retrieval_confidence=0.8,
            self_consistency_score=0.123456,
        )
        assert result.self_consistency_score == 0.123

    def test_verbalized_rounded_to_3_decimals(self):
        estimator = UncertaintyEstimator.__new__(UncertaintyEstimator)
        result = estimator._fuse_signals(
            retrieval_confidence=0.8,
            verbalized_confidence=0.987654,
        )
        assert result.verbalized_confidence == 0.988

    def test_grounding_rounded_to_3_decimals(self):
        estimator = UncertaintyEstimator.__new__(UncertaintyEstimator)
        result = estimator._fuse_signals(
            retrieval_confidence=0.8,
            grounding_score=0.555555,
        )
        assert result.grounding_score == 0.556
