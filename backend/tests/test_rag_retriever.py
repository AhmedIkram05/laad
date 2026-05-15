"""Tests for RAG retriever module."""

import pytest
from unittest.mock import MagicMock, patch


class TestRAGRetriever:
    """Test cases for RAGRetriever class."""

    @patch("backend.src.rag.retriever.chromadb.HttpClient")
    def test_retriever_initialization(self, mock_client):
        """Test retriever can be initialized."""
        from backend.src.rag.retriever import RAGRetriever

        with patch("backend.src.rag.retriever.config") as mock_config:
            mock_config.chroma_host = "localhost"
            mock_config.chroma_port = 8001
            mock_config.chroma_collection = "atm_logs"
            mock_config.retrieval_top_k = 5

            with patch.object(RAGRetriever, "_build_client", return_value=MagicMock()):
                with patch.object(RAGRetriever, "_get_collection", return_value=MagicMock()):
                    retriever = RAGRetriever()
                    assert retriever is not None

    def test_calculate_confidence(self):
        """Test confidence calculation from distance."""
        from backend.src.rag.retriever import RAGRetriever

        with patch("backend.src.rag.retriever.chromadb.HttpClient"):
            retriever = RAGRetriever.__new__(RAGRetriever)

        assert retriever._calculate_confidence(0.0) == 1.0
        assert retriever._calculate_confidence(0.5) == 0.5
        assert retriever._calculate_confidence(1.0) == 0.0
        assert retriever._calculate_confidence(None) == 0.5


class TestRetrievedChunk:
    """Test cases for RetrievedChunk dataclass."""

    def test_chunk_creation(self):
        from backend.src.rag.retriever import RetrievedChunk

        chunk = RetrievedChunk(
            text="Test log entry",
            chunk_id="chunk_1",
            atm_id="ATM-GB-0001",
            timestamp="2026-05-15T10:00:00Z",
            distance=0.2,
            confidence_score=0.8,
        )

        assert chunk.text == "Test log entry"
        assert chunk.atm_id == "ATM-GB-0001"
        assert chunk.confidence_score == 0.8

    def test_retrieve_returns_chunks(self):
        from backend.src.rag.retriever import RAGRetriever

        mock_collection = MagicMock()
        mock_collection.query.return_value = {
            "documents": [["log entry 1", "log entry 2"]],
            "metadatas": [[{"atm_id": "ATM-GB-0001", "last_timestamp": "2026-05-15T10:00:00Z"}, {"atm_id": "ATM-GB-0002", "last_timestamp": "2026-05-15T10:01:00Z"}]],
            "distances": [[0.2, 0.3]],
            "ids": [["doc_1", "doc_2"]],
        }

        with patch.object(RAGRetriever, "_build_client", return_value=MagicMock()):
            with patch.object(RAGRetriever, "_get_collection", return_value=mock_collection):
                retriever = RAGRetriever()
                chunks = retriever.retrieve(query="test", top_k=2)

        assert len(chunks) == 2
        assert chunks[0].text == "log entry 1"
        assert chunks[0].chunk_id == "doc_1"
        assert chunks[0].atm_id == "ATM-GB-0001"
        assert chunks[0].distance == 0.2

    def test_retrieve_returns_empty_on_error(self):
        from backend.src.rag.retriever import RAGRetriever

        mock_collection = MagicMock()
        mock_collection.query.side_effect = Exception("Connection failed")

        with patch.object(RAGRetriever, "_build_client", return_value=MagicMock()):
            with patch.object(RAGRetriever, "_get_collection", return_value=mock_collection):
                retriever = RAGRetriever()
                chunks = retriever.retrieve(query="test")

        assert chunks == []

    def test_retrieve_by_atm(self):
        from backend.src.rag.retriever import RAGRetriever

        mock_collection = MagicMock()
        mock_collection.get.return_value = {
            "documents": ["log 1", "log 2"],
            "metadatas": [{"last_timestamp": "2026-05-15T10:00:00Z"}, {"last_timestamp": "2026-05-15T10:01:00Z"}],
            "ids": ["id_1", "id_2"],
        }

        with patch.object(RAGRetriever, "_build_client", return_value=MagicMock()):
            with patch.object(RAGRetriever, "_get_collection", return_value=mock_collection):
                retriever = RAGRetriever()
                chunks = retriever.retrieve_by_atm(atm_id="ATM-GB-0001", limit=2)

        assert len(chunks) == 2
        assert chunks[0].atm_id == "ATM-GB-0001"

    def test_get_collection_stats(self):
        from backend.src.rag.retriever import RAGRetriever

        mock_collection = MagicMock()
        mock_collection.count.return_value = 100

        with patch.object(RAGRetriever, "_build_client", return_value=MagicMock()):
            with patch.object(RAGRetriever, "_get_collection", return_value=mock_collection):
                retriever = RAGRetriever()
                stats = retriever.get_collection_stats()

        assert stats["total_chunks"] == 100