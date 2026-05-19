"""Tests for RAG uncertainty estimation module (retrieval-only confidence)."""

import pytest
from unittest.mock import MagicMock, patch


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


class TestUncertaintyEstimator:
    """Test cases for UncertaintyEstimator class (retrieval-only)."""

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


class TestUncertaintyEstimate:
    """Test cases for UncertaintyEstimate dataclass."""

    def test_estimate_creation(self):
        from backend.src.rag.uncertainty import UncertaintyEstimate

        estimate = UncertaintyEstimate(
            final_confidence=0.85,
            confidence_level="high",
            self_consistency_score=0.85,
            verbalized_confidence=None,
            generation_variance=None,
            is_uncertain=False,
            recommendation="Auto-respond",
        )

        assert estimate.final_confidence == 0.85
        assert estimate.confidence_level == "high"
        assert estimate.is_uncertain is False

    def test_estimate_returns_retrieval_confidence(self):
        """Test that uncertainty uses retrieval confidence (no LLM call)."""
        from backend.src.rag.uncertainty import UncertaintyEstimator
        from backend.src.rag.retriever import RetrievedChunk

        estimator = UncertaintyEstimator()

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

        result = estimator.estimate(query="test", chunks=chunks)

        assert result.final_confidence > 0
        assert result.confidence_level in ("high", "medium", "low")
        assert result.verbalized_confidence is None
        assert result.generation_variance is None

    def test_estimate_empty_chunks(self):
        """Test estimate with no chunks."""
        from backend.src.rag.uncertainty import UncertaintyEstimator

        estimator = UncertaintyEstimator()
        result = estimator.estimate(query="test", chunks=[])

        assert result.final_confidence == 0.0
        assert result.confidence_level == "low"
        assert result.is_uncertain is True
