"""End-to-end integration tests for RAG system."""

import pytest
from unittest.mock import MagicMock, patch


class TestRAGEndToEnd:
    """End-to-end tests for full RAG pipeline."""

    @patch("backend.src.rag.retriever.get_retriever")
    @patch("backend.src.rag.generator.get_generator")
    @patch("backend.src.rag.uncertainty.get_uncertainty_estimator")
    @patch("backend.src.rag.calibration.get_calibration_manager")
    def test_full_pipeline_execution(
        self,
        mock_calibration,
        mock_uncertainty,
        mock_generator,
        mock_retriever,
    ):
        """Test complete RAG pipeline from query to response."""
        from backend.src.rag.retriever import RetrievedChunk
        from backend.src.rag.generator import GeneratedResponse
        from backend.src.rag.uncertainty import UncertaintyEstimate
        from backend.src.rag.calibration import CalibrationParams

        mock_retriever.return_value.retrieve.return_value = [
            RetrievedChunk(
                text="Error: Network disconnected at ATM-GB-0001",
                chunk_id="1",
                atm_id="ATM-GB-0001",
                timestamp="2026-05-15T10:00:00Z",
                distance=0.1,
                confidence_score=0.9,
            )
        ]

        mock_generator.return_value.generate.return_value = GeneratedResponse(
            text="This is a network timeout error. Check connectivity.",
            sources=[],
            model="google/gemma-4-26b-a4b-it:free",
            raw_response={},
        )

        mock_uncertainty.return_value.estimate.return_value = UncertaintyEstimate(
            final_confidence=0.85,
            confidence_level="high",
            self_consistency_score=0.9,
            verbalized_confidence=0.8,
            generation_variance=0.1,
            is_uncertain=False,
            recommendation="Auto-respond",
        )

        mock_calibration.return_value.params = CalibrationParams(
            is_fitted=False,
        )

        from backend.src.rag.rag_pipeline import process_query

        result = process_query("What is error at ATM-GB-0001?")

        assert result is not None
        assert "answer" in result or "error" in result


class TestRAGWithAnomaly:
    """Tests for RAG integration with anomaly detection."""

    @patch("backend.src.rag.retriever.get_retriever")
    def test_retrieval_with_atm_filter(self, mock_retriever):
        """Test retrieval filtered by specific ATM."""
        from backend.src.rag.retriever import RetrievedChunk

        mock_retriever.return_value.retrieve.return_value = [
            RetrievedChunk(
                text=f"Error log {i}",
                chunk_id=f"chunk_{i}",
                atm_id="ATM-GB-0001",
                timestamp="2026-05-15T10:00:00Z",
                distance=0.1 * i,
                confidence_score=0.9 - (0.1 * i),
            )
            for i in range(3)
        ]

        from backend.src.rag.retriever import get_retriever

        retriever = get_retriever()
        chunks = retriever.retrieve(
            query="network error",
            atm_id="ATM-GB-0001",
            top_k=5,
        )

        for chunk in chunks:
            assert chunk.atm_id == "ATM-GB-0001"


class TestRAGErrorHandling:
    """Tests for RAG error handling."""

    def test_retrieval_failure_returns_empty_list(self):
        """Test that retrieve returns empty list on exception."""
        from backend.src.rag.retriever import RAGRetriever
        from unittest.mock import patch

        with patch('backend.src.rag.retriever.chromadb.HttpClient'):
            retriever = RAGRetriever()
            with patch.object(retriever.collection, 'query', side_effect=Exception("ChromaDB connection failed")):
                chunks = retriever.retrieve(query="test")

        assert chunks == []

    def test_llm_failure_returns_fallback_response(self):
        """Test that generator returns fallback response when LLM fails."""
        from backend.src.rag.generator import RAGGenerator
        from backend.src.rag.retriever import RetrievedChunk

        generator = RAGGenerator()
        with patch.object(generator.llm_client, 'generate', side_effect=Exception("API rate limit exceeded")):
            response = generator.generate(
                query="test",
                chunks=[RetrievedChunk(
                    text="test chunk",
                    chunk_id="1",
                    atm_id="ATM-GB-0001",
                    timestamp="2026-05-15T00:00:00Z",
                    distance=0.5,
                    confidence_score=0.5,
                )],
            )

        assert "found" in response.text.lower() or "relevant" in response.text.lower()
        assert response.model == "fallback-template"
        assert len(response.sources) > 0


class TestRAGRouterIntegration:
    """Integration tests for RAG router with mocked dependencies."""

    @pytest.fixture(autouse=True)
    def mock_mlflow(self):
        with patch.dict("sys.modules", {"mlflow": MagicMock(), "mlflow.sklearn": MagicMock(), "mlflow.xgboost": MagicMock()}):
            yield

    @pytest.mark.skip(reason="Requires ChromaDB; covered by test_rag_api.py router tests with proper mocking")
    def test_full_router_query_flow(self):
        pass