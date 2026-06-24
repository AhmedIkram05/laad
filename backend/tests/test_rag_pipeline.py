"""Tests for backend.src.rag.rag_pipeline."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


class TestProcessQuery:
    def test_success_path(self):
        mock_chunks = [
            MagicMock(
                text="Chunk 1",
                chunk_id="c1",
                atm_id="ATM-001",
                timestamp="2026-03-05T09:00:00Z",
                confidence_score=0.9,
            )
        ]
        mock_retriever = MagicMock()
        mock_retriever.retrieve.return_value = mock_chunks

        mock_generator = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "Generated answer"
        mock_response.model = "test-model"
        mock_response.sources = mock_chunks
        mock_response.self_consistency_score = 0.95
        mock_response.verbalized_confidence = 0.9
        mock_response.grounding_score = 0.85
        mock_response.cross_encoder_used = True
        mock_response.was_revised = False
        mock_generator.generate.return_value = mock_response

        mock_uncertainty = MagicMock()
        mock_estimate = MagicMock()
        mock_estimate.final_confidence = 0.15
        mock_estimate.confidence_level = "high"
        mock_estimate.is_uncertain = False
        mock_estimate.recommendation = ""
        mock_estimate.generation_variance = 0.1
        mock_uncertainty.estimate.return_value = mock_estimate

        with patch(
            "backend.src.rag.rag_pipeline.get_retriever", return_value=mock_retriever
        ):
            with patch(
                "backend.src.rag.rag_pipeline.get_generator",
                return_value=mock_generator,
            ):
                with patch(
                    "backend.src.rag.rag_pipeline.get_uncertainty_estimator",
                    return_value=mock_uncertainty,
                ):
                    from backend.src.rag.rag_pipeline import process_query

                    result = process_query("test query", atm_id="ATM-001", top_k=3)

        assert result["answer"] == "Generated answer"
        assert result["model_used"] == "test-model"
        assert result["uncertainty_score"] == 0.15
        assert result["confidence_level"] == "high"
        assert len(result["sources"]) == 1
        assert result["sources"][0]["chunk_id"] == "c1"

    def test_error_path_returns_fallback(self):
        with patch(
            "backend.src.rag.rag_pipeline.get_retriever",
            side_effect=Exception("Retriever error"),
        ):
            from backend.src.rag.rag_pipeline import process_query

            result = process_query("test query")

        assert "error" in result
        assert "answer" in result
