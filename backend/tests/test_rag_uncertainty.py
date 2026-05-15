"""Tests for RAG uncertainty estimation module."""

import pytest
from unittest.mock import MagicMock, patch


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

    def test_text_similarity(self):
        """Test text similarity calculation."""
        from backend.src.rag.uncertainty import UncertaintyEstimator

        estimator = UncertaintyEstimator.__new__(UncertaintyEstimator)

        similarity = estimator._text_similarity(
            "hello world test",
            "hello world example"
        )
        assert 0 < similarity < 1

        identical = estimator._text_similarity("same text", "same text")
        assert identical == 1.0

        different = estimator._text_similarity("abc", "xyz")
        assert different == 0.0

    def test_variance_calculation(self):
        """Test variance calculation for response lengths."""
        from backend.src.rag.uncertainty import UncertaintyEstimator
        from backend.src.rag.llm_client import LLMResponse

        estimator = UncertaintyEstimator.__new__(UncertaintyEstimator)

        responses = [
            LLMResponse(text="Short", raw_response={}, model="test", finish_reason="stop"),
            LLMResponse(text="Medium length response", raw_response={}, model="test", finish_reason="stop"),
            LLMResponse(text="Much longer response text here", raw_response={}, model="test", finish_reason="stop"),
        ]

        variance = estimator._calculate_variance(responses)
        assert variance > 0

        empty_variance = estimator._calculate_variance([])
        assert empty_variance == 0.0

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
            self_consistency_score=0.9,
            verbalized_confidence=0.8,
            generation_variance=0.1,
            is_uncertain=False,
            recommendation="Auto-respond",
        )

        assert estimate.final_confidence == 0.85
        assert estimate.confidence_level == "high"
        assert estimate.is_uncertain is False

    @patch("backend.src.rag.uncertainty.get_generator")
    @patch("backend.src.rag.uncertainty.get_llm_client")
    def test_estimate_returns_result(self, mock_llm, mock_gen):
        from backend.src.rag.uncertainty import UncertaintyEstimator, get_uncertainty_estimator
        from backend.src.rag.retriever import RetrievedChunk
        from backend.src.rag.llm_client import LLMResponse

        mock_llm.return_value.generate.return_value = LLMResponse(
            text="Test answer CONFIDENCE: 0.8",
            raw_response={},
            model="test",
            finish_reason="stop",
        )
        mock_gen.return_value = MagicMock()

        estimator = UncertaintyEstimator()
        estimator.num_samples = 1

        chunks = [
            RetrievedChunk(
                text="test log data",
                chunk_id="1",
                atm_id="ATM-GB-0001",
                timestamp="2026-05-15T10:00:00Z",
                distance=0.3,
                confidence_score=0.7,
            )
        ]

        result = estimator.estimate(query="test", chunks=chunks)

        assert result.final_confidence > 0
        assert result.confidence_level in ("high", "medium", "low")
        assert isinstance(result.self_consistency_score, float)