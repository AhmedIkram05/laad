"""Tests for RAG uncertainty estimation with multi-signal fusion."""

import pytest


class TestRetrievalConfidence:
    """Test cases for retrieval-only confidence computation."""

    def test_compute_retrieval_confidence_single_chunk(self):
        """Test confidence with a single relevant chunk."""
        from backend.src.rag.uncertainty import compute_retrieval_confidence
        from backend.src.rag.retriever import RetrievedChunk

        chunks = [
            RetrievedChunk(
                text="test log data",
                chunk_id="1",
                atm_id="ATM-GB-0001",
                timestamp="2026-05-15T10:00:00Z",
                distance=0.2,
                confidence_score=0.8,
            )
        ]

        result = compute_retrieval_confidence(chunks)
        assert result > 0.0
        assert result <= 1.0

    def test_compute_retrieval_confidence_multiple_chunks(self):
        """Test confidence with multiple chunks from different ATMs."""
        from backend.src.rag.uncertainty import compute_retrieval_confidence
        from backend.src.rag.retriever import RetrievedChunk

        chunks = [
            RetrievedChunk(
                text="log 1",
                chunk_id="1",
                atm_id="ATM-GB-0001",
                timestamp="2026-05-15T10:00:00Z",
                distance=0.1,
                confidence_score=0.9,
            ),
            RetrievedChunk(
                text="log 2",
                chunk_id="2",
                atm_id="ATM-GB-0002",
                timestamp="2026-05-15T10:01:00Z",
                distance=0.2,
                confidence_score=0.8,
            ),
            RetrievedChunk(
                text="log 3",
                chunk_id="3",
                atm_id="ATM-GB-0003",
                timestamp="2026-05-15T10:02:00Z",
                distance=0.3,
                confidence_score=0.7,
            ),
        ]

        result = compute_retrieval_confidence(chunks)
        assert result > 0.7
        assert result <= 1.0

    def test_compute_retrieval_confidence_empty(self):
        """Test confidence with empty chunks."""
        from backend.src.rag.uncertainty import compute_retrieval_confidence

        result = compute_retrieval_confidence([])
        assert result == 0.0

    def test_compute_retrieval_confidence_high_distance(self):
        """Test confidence with high distance (low relevance)."""
        from backend.src.rag.uncertainty import compute_retrieval_confidence
        from backend.src.rag.retriever import RetrievedChunk

        chunks = [
            RetrievedChunk(
                text="irrelevant log",
                chunk_id="1",
                atm_id="ATM-GB-0001",
                timestamp="2026-05-15T10:00:00Z",
                distance=0.9,
                confidence_score=0.1,
            )
        ]

        result = compute_retrieval_confidence(chunks)
        assert result < 0.3

    def test_compute_retrieval_confidence_same_atm(self):
        """Test confidence bonus for diverse ATMs."""
        from backend.src.rag.uncertainty import compute_retrieval_confidence
        from backend.src.rag.retriever import RetrievedChunk

        chunks_same = [
            RetrievedChunk(
                text="log 1",
                chunk_id="1",
                atm_id="ATM-GB-0001",
                timestamp="2026-05-15T10:00:00Z",
                distance=0.2,
                confidence_score=0.8,
            ),
            RetrievedChunk(
                text="log 2",
                chunk_id="2",
                atm_id="ATM-GB-0001",
                timestamp="2026-05-15T10:01:00Z",
                distance=0.3,
                confidence_score=0.7,
            ),
        ]

        chunks_diverse = [
            RetrievedChunk(
                text="log 1",
                chunk_id="1",
                atm_id="ATM-GB-0001",
                timestamp="2026-05-15T10:00:00Z",
                distance=0.2,
                confidence_score=0.8,
            ),
            RetrievedChunk(
                text="log 2",
                chunk_id="2",
                atm_id="ATM-GB-0002",
                timestamp="2026-05-15T10:01:00Z",
                distance=0.3,
                confidence_score=0.7,
            ),
        ]

        same = compute_retrieval_confidence(chunks_same)
        diverse = compute_retrieval_confidence(chunks_diverse)
        assert diverse >= same


class TestMultiSignalFusion:
    """Test cases for multi-signal confidence fusion."""

    def test_fusion_retrieval_only(self):
        """Test fusion falls back to retrieval when no agentic signals."""
        from backend.src.rag.uncertainty import UncertaintyEstimator
        from backend.src.rag.retriever import RetrievedChunk

        estimator = UncertaintyEstimator()
        chunks = [  # noqa: F841
            RetrievedChunk(text="log", chunk_id="1", atm_id="ATM-GB-0001",
                           timestamp="2026-05-15T10:00:00Z", distance=0.2, confidence_score=0.8)
        ]
        result = estimator._fuse_signals(retrieval_confidence=0.8)
        assert result.final_confidence == 0.8
        assert result.self_consistency_score is None
        assert result.verbalized_confidence is None
        assert result.grounding_score is None

    def test_fusion_all_signals(self):
        """Test fusion with all 4 signals."""
        from backend.src.rag.uncertainty import UncertaintyEstimator

        estimator = UncertaintyEstimator()
        result = estimator._fuse_signals(
            retrieval_confidence=0.8,
            self_consistency_score=0.9,
            verbalized_confidence=0.85,
            grounding_score=0.95,
        )
        assert 0.8 <= result.final_confidence <= 1.0
        assert result.self_consistency_score == 0.9
        assert result.verbalized_confidence == 0.85
        assert result.grounding_score == 0.95
        assert result.generation_variance == pytest.approx(0.1, rel=0.01)

    def test_fusion_low_consistency_lowers_confidence(self):
        """Test that low self-consistency reduces final confidence."""
        from backend.src.rag.uncertainty import UncertaintyEstimator

        estimator = UncertaintyEstimator()

        high_consistency = estimator._fuse_signals(
            retrieval_confidence=0.9,
            self_consistency_score=0.95,
            verbalized_confidence=0.9,
            grounding_score=0.9,
        )
        low_consistency = estimator._fuse_signals(
            retrieval_confidence=0.9,
            self_consistency_score=0.3,
            verbalized_confidence=0.9,
            grounding_score=0.9,
        )

        assert high_consistency.final_confidence > low_consistency.final_confidence

    def test_fusion_poor_grounding_lowers_confidence(self):
        """Test that poor citation grounding reduces final confidence."""
        from backend.src.rag.uncertainty import UncertaintyEstimator

        estimator = UncertaintyEstimator()

        good_grounding = estimator._fuse_signals(
            retrieval_confidence=0.9,
            self_consistency_score=0.9,
            verbalized_confidence=0.9,
            grounding_score=0.95,
        )
        poor_grounding = estimator._fuse_signals(
            retrieval_confidence=0.9,
            self_consistency_score=0.9,
            verbalized_confidence=0.9,
            grounding_score=0.2,
        )

        assert good_grounding.final_confidence > poor_grounding.final_confidence

    def test_fusion_empty_chunks(self):
        """Test fusion with no chunks returns zero confidence."""
        from backend.src.rag.uncertainty import UncertaintyEstimator

        estimator = UncertaintyEstimator()
        result = estimator.estimate(query="test", chunks=[],
                                     self_consistency_score=0.8,
                                     verbalized_confidence=0.8,
                                     grounding_score=0.8)
        assert result.final_confidence == 0.0
        assert result.is_uncertain is True

    def test_fusion_with_generation_variance(self):
        """Test that generation_variance is computed as 1 - consistency."""
        from backend.src.rag.uncertainty import UncertaintyEstimator

        estimator = UncertaintyEstimator()
        result = estimator._fuse_signals(
            retrieval_confidence=0.8,
            self_consistency_score=0.85,
        )
        assert result.generation_variance is not None
        assert result.generation_variance == pytest.approx(0.15, rel=0.01)


class TestUncertaintyEstimator:
    """Test cases for UncertaintyEstimator class."""

    def test_confidence_classification(self):
        """Test confidence level classification."""
        from backend.src.rag.uncertainty import UncertaintyEstimator

        estimator = UncertaintyEstimator.__new__(UncertaintyEstimator)

        assert estimator._classify_confidence(0.9) == "high"
        assert estimator._classify_confidence(0.8) == "high"
        assert estimator._classify_confidence(0.7) == "medium"
        assert estimator._classify_confidence(0.5) == "medium"
        assert estimator._classify_confidence(0.4) == "low"
        assert estimator._classify_confidence(0.1) == "low"

    def test_recommendation_generation(self):
        """Test recommendation based on confidence level."""
        from backend.src.rag.uncertainty import UncertaintyEstimator

        estimator = UncertaintyEstimator.__new__(UncertaintyEstimator)

        high_rec = estimator._get_recommendation(0.9, "high")
        assert "Auto-respond" in high_rec

        med_rec = estimator._get_recommendation(0.6, "medium")
        assert "Verify" in med_rec

        low_rec = estimator._get_recommendation(0.3, "low")
        assert "Escalate" in low_rec

    def test_estimate_passes_agentic_signals(self):
        """Test estimate method correctly passes and fuses agentic signals."""
        from backend.src.rag.uncertainty import UncertaintyEstimator
        from backend.src.rag.retriever import RetrievedChunk

        estimator = UncertaintyEstimator()
        chunks = [  # noqa: F841
            RetrievedChunk(text="log", chunk_id="1", atm_id="ATM-GB-0001",
                           timestamp="2026-05-15T10:00:00Z", distance=0.2, confidence_score=0.8)
        ]

        result = estimator.estimate(
            query="test",
            chunks=chunks,
            self_consistency_score=0.88,
            verbalized_confidence=0.92,
            grounding_score=0.96,
        )

        assert result.final_confidence > 0
        assert result.self_consistency_score == 0.88
        assert result.verbalized_confidence == 0.92
        assert result.grounding_score == 0.96
        assert result.generation_variance is not None

    def test_estimate_no_agentic_signals(self):
        """Test estimate with only retrieval fails gracefully."""
        from backend.src.rag.uncertainty import UncertaintyEstimator
        from backend.src.rag.retriever import RetrievedChunk

        estimator = UncertaintyEstimator()
        chunks = [
            RetrievedChunk(text="log", chunk_id="1", atm_id="ATM-GB-0001",
                           timestamp="2026-05-15T10:00:00Z", distance=0.2, confidence_score=0.8)
        ]

        result = estimator.estimate(query="test", chunks=chunks)

        assert result.final_confidence > 0
        assert result.self_consistency_score is None
        assert result.verbalized_confidence is None
        assert result.grounding_score is None
