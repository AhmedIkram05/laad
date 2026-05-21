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
            top_k=3,
            include_uncertainty=True,
        )

        assert request.query == "What is error A1?"
        assert request.atm_id == "ATM-GB-0001"
        assert request.top_k == 3
        assert request.include_uncertainty is True

    def test_rag_query_request_defaults(self):
        from backend.src.rag.schemas import RAGQueryRequest

        request = RAGQueryRequest(query="Test query")

        assert request.atm_id is None
        assert request.top_k == 10
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

            is_uncertain=False,
            recommendation="Auto-respond",
            model_used="google/gemma-4-26b-a4b-it:free",
            self_consistency_score=0.88,
            verbalized_confidence=0.92,
            grounding_score=0.95,
            cross_encoder_used=True,
            was_revised=False,
        )

        assert response.query_id == 42
        assert response.answer == "The error means..."
        assert response.confidence_level == "high"
        assert response.self_consistency_score == 0.88
        assert response.verbalized_confidence == 0.92
        assert response.grounding_score == 0.95
        assert response.cross_encoder_used is True
        assert response.was_revised is False

    def test_rag_query_response_with_fallback_model(self):
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
            query_id=43,
            answer="I found 3 relevant log entries...",
            sources=sources,
            uncertainty_score=0.6,
            confidence_level="medium",

            is_uncertain=False,
            recommendation="Verify - moderate confidence",
            model_used="fallback-template",
        )

        assert response.model_used == "fallback-template"
        assert response.query_id == 43
        assert response.self_consistency_score is None


class TestRAGFeedback:
    """Test cases for RAG feedback schemas."""

    def test_feedback_request(self):
        from backend.src.rag.schemas import RAGFeedbackRequest
        from pydantic import ValidationError

        req = RAGFeedbackRequest(query_id=1, feedback="helpful")
        assert req.feedback == "helpful"

        req_uncertain = RAGFeedbackRequest(query_id=1, feedback="uncertain")
        assert req_uncertain.feedback == "uncertain"

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
        with patch.dict("sys.modules", {"mlflow": MagicMock(), "mlflow.sklearn": MagicMock(), "mlflow.xgboost": MagicMock()}):
            yield

    @pytest.fixture
    def client(self):
        from backend.src.api.server import app
        return TestClient(app)

    @patch("backend.src.rag.router.get_retriever")
    @patch("backend.src.rag.router.get_generator")
    @patch("backend.src.rag.router.get_uncertainty_estimator")
    @patch("backend.src.rag.router._get_user_id_from_username")
    def test_query_returns_404_no_chunks(self, mock_user_id, mock_unc, mock_gen, mock_ret, client):
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
    @patch("backend.src.rag.router.get_retriever")
    @patch("backend.src.rag.router.get_generator")
    @patch("backend.src.rag.router.get_uncertainty_estimator")
    @patch("backend.src.rag.router.get_cached_response")
    @patch("backend.src.rag.router.set_cached_response")
    def test_query_rate_limiting(self, mock_set_cache, mock_get_cache, mock_unc, mock_gen, mock_ret, mock_user_id, client):
        from backend.src.rag.retriever import RetrievedChunk
        from backend.src.rag.generator import GeneratedResponse
        from backend.src.rag.uncertainty import UncertaintyEstimate
        from backend.src.rag import router as rag_router

        rag_router._query_timestamps.clear()

        mock_user_id.return_value = 1
        mock_get_cache.return_value = None
        mock_ret.return_value.retrieve.return_value = [
            RetrievedChunk(
                text="Network timeout at ATM-GB-0001",
                chunk_id="doc_1",
                atm_id="ATM-GB-0001",
                timestamp="2026-05-15T10:00:00Z",
                distance=0.1,
                confidence_score=0.9,
            )
        ]
        mock_gen.return_value.generate.return_value = GeneratedResponse(
            text="This is a network timeout error.",
            sources=[],
            model="test-model",
            raw_response={},
        )
        mock_unc.return_value.estimate.return_value = UncertaintyEstimate(
            final_confidence=0.85,
            confidence_level="high",
            self_consistency_score=0.85,
            verbalized_confidence=None,
            generation_variance=None,
            grounding_score=None,
            is_uncertain=False,
            recommendation="Auto-respond",
        )

        token_resp = client.post("/auth/login", data={"username": "admin", "password": "admin"})
        token = token_resp.json()["access_token"]

        with patch("backend.src.rag.router.get_redis_client", return_value=None):
            for i in range(rag_router.RATE_LIMIT_MAX_REQUESTS):
                resp = client.post(
                    "/api/rag/query",
                    json={"query": f"test query {i}"},
                    headers={"Authorization": f"Bearer {token}"},
                )
                assert resp.status_code == 200

            resp = client.post(
                "/api/rag/query",
                json={"query": "rate limited query"},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == 429
            assert "Rate limit exceeded" in resp.json()["detail"]
