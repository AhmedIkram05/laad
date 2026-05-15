"""Tests for RAG API router and schemas."""

import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient


class TestRAGSchemas:
    """Test cases for RAG Pydantic schemas."""

    def test_rag_query_request_valid(self):
        from backend.src.rag.schemas import RAGQueryRequest

        request = RAGQueryRequest(
            query="What is error A1?",
            atm_id="ATM-GB-0001",
            top_k=5,
            include_uncertainty=True,
        )

        assert request.query == "What is error A1?"
        assert request.atm_id == "ATM-GB-0001"
        assert request.top_k == 5
        assert request.include_uncertainty is True

    def test_rag_query_request_defaults(self):
        from backend.src.rag.schemas import RAGQueryRequest

        request = RAGQueryRequest(query="Test query")

        assert request.atm_id is None
        assert request.top_k == 5
        assert request.include_uncertainty is True

    def test_rag_query_request_validation(self):
        from backend.src.rag.schemas import RAGQueryRequest
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            RAGQueryRequest(query="")

        with pytest.raises(ValidationError):
            RAGQueryRequest(query="a" * 1001)

    def test_source_chunk(self):
        from backend.src.rag.schemas import SourceChunk

        chunk = SourceChunk(
            text="Error log entry",
            chunk_id="chunk_1",
            atm_id="ATM-GB-0001",
            timestamp="2026-05-15T10:00:00Z",
            confidence_score=0.85,
        )

        assert chunk.text == "Error log entry"
        assert chunk.confidence_score == 0.85

    def test_rag_query_response(self):
        from backend.src.rag.schemas import RAGQueryResponse, SourceChunk

        sources = [
            SourceChunk(
                text="Log 1",
                chunk_id="1",
                atm_id="ATM-GB-0001",
                timestamp="2026-05-15T10:00:00Z",
                confidence_score=0.9,
            )
        ]

        response = RAGQueryResponse(
            query_id=42,
            answer="The error means...",
            sources=sources,
            uncertainty_score=0.85,
            confidence_level="high",
            is_calibrated=True,
            is_uncertain=False,
            recommendation="Auto-respond",
            model_used="gemini-2.0-flash",
        )

        assert response.query_id == 42
        assert response.answer == "The error means..."
        assert response.confidence_level == "high"


class TestRAGFeedback:
    """Test cases for RAG feedback schemas."""

    def test_feedback_request(self):
        from backend.src.rag.schemas import RAGFeedbackRequest
        from pydantic import ValidationError

        req = RAGFeedbackRequest(query_id=1, feedback="helpful")
        assert req.feedback == "helpful"

        with pytest.raises(ValidationError):
            RAGFeedbackRequest(query_id=1, feedback="invalid")

    def test_feedback_response(self):
        from backend.src.rag.schemas import RAGFeedbackResponse

        response = RAGFeedbackResponse(
            success=True,
            message="Feedback recorded",
        )

        assert response.success is True
        assert response.message == "Feedback recorded"


class TestRAGRouter:
    """Test cases for RAG FastAPI routes."""

    @pytest.fixture(autouse=True)
    def mock_mlflow(self):
        with patch.dict("sys.modules", {"mlflow": MagicMock(), "mlflow.sklearn": MagicMock()}):
            yield

    @pytest.fixture
    def client(self):
        from backend.src.api.server import app
        return TestClient(app)

    @patch("backend.src.rag.router.get_retriever")
    @patch("backend.src.rag.router.get_generator")
    @patch("backend.src.rag.router.get_uncertainty_estimator")
    @patch("backend.src.rag.router.get_calibration_manager")
    @patch("backend.src.rag.router._get_user_id_from_username")
    def test_query_returns_404_no_chunks(self, mock_user_id, mock_cal, mock_unc, mock_gen, mock_ret, client):
        mock_user_id.return_value = 1
        mock_ret.return_value.retrieve.return_value = []

        token_resp = client.post("/auth/login", data={"username": "admin", "password": "admin"})
        token = token_resp.json()["access_token"]

        resp = client.post(
            "/api/rag/query",
            json={"query": "test"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 404

    @patch("backend.src.rag.router._get_user_id_from_username")
    def test_recalibrate_requires_admin(self, mock_user_id, client):
        mock_user_id.return_value = 1

        token_resp = client.post("/auth/login", data={"username": "admin", "password": "admin"})
        token = token_resp.json()["access_token"]

        resp = client.post(
            "/api/rag/recalibrate",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
