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
                chunks = retriever.retrieve(query="test", top_k=2, temporal_boost=False, most_recent_first=False)

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

    def test_get_collection_stats_on_error(self):
        from backend.src.rag.retriever import RAGRetriever

        mock_collection = MagicMock()
        mock_collection.count.side_effect = Exception("Connection failed")

        with patch.object(RAGRetriever, "_build_client", return_value=MagicMock()):
            with patch.object(RAGRetriever, "_get_collection", return_value=mock_collection):
                retriever = RAGRetriever()
                stats = retriever.get_collection_stats()

        assert "error" in stats

    def test_retrieve_with_anomaly_type_filter(self):
        """Test retrieval filtered by anomaly type."""
        from backend.src.rag.retriever import RAGRetriever

        mock_collection = MagicMock()
        mock_collection.query.return_value = {
            "documents": [["log entry with A1 tag"]],
            "metadatas": [[{"atm_id": "ATM-GB-0001", "last_timestamp": "2026-05-15T10:00:00Z", "_anomaly_tag": "A1"}]],
            "distances": [[0.2]],
            "ids": [["doc_1"]],
        }

        with patch.object(RAGRetriever, "_build_client", return_value=MagicMock()):
            with patch.object(RAGRetriever, "_get_collection", return_value=mock_collection):
                retriever = RAGRetriever()
                chunks = retriever.retrieve(query="network timeout", anomaly_type="A1", error_only=False)

        assert len(chunks) == 1
        mock_collection.query.assert_called_once()
        call_kwargs = mock_collection.query.call_args[1]
        assert call_kwargs["where"] == {"_anomaly_tag": "A1"}

    def test_retrieve_with_combined_filters(self):
        """Test retrieval with both atm_id and anomaly_type filters."""
        from backend.src.rag.retriever import RAGRetriever

        mock_collection = MagicMock()
        mock_collection.query.return_value = {
            "documents": [["log entry"]],
            "metadatas": [[{"atm_id": "ATM-GB-0001", "last_timestamp": "2026-05-15T10:00:00Z"}]],
            "distances": [[0.3]],
            "ids": [["doc_1"]],
        }

        with patch.object(RAGRetriever, "_build_client", return_value=MagicMock()):
            with patch.object(RAGRetriever, "_get_collection", return_value=mock_collection):
                retriever = RAGRetriever()
                chunks = retriever.retrieve(
                    query="test",
                    atm_id="ATM-GB-0001",
                    anomaly_type="A3",
                    error_only=False,
                )

        call_kwargs = mock_collection.query.call_args[1]
        assert call_kwargs["where"] == {"$and": [{"atm_id": "ATM-GB-0001"}, {"_anomaly_tag": "A3"}]}

    def test_retrieve_with_temporal_boost(self):
        """Test that temporal boost is applied when enabled."""
        from backend.src.rag.retriever import RAGRetriever

        mock_collection = MagicMock()
        mock_collection.query.return_value = {
            "documents": [["recent log", "old log"]],
            "metadatas": [
                [{"atm_id": "ATM-GB-0001", "last_timestamp": "2026-05-19T10:00:00Z"},
                 {"atm_id": "ATM-GB-0001", "last_timestamp": "2026-05-18T10:00:00Z"}]
            ],
            "distances": [[0.5, 0.5]],
            "ids": [["doc_1", "doc_2"]],
        }

        with patch.object(RAGRetriever, "_build_client", return_value=MagicMock()):
            with patch.object(RAGRetriever, "_get_collection", return_value=mock_collection):
                retriever = RAGRetriever()
                chunks = retriever.retrieve(query="test", temporal_boost=True)

        assert len(chunks) == 2

    def test_retrieve_without_temporal_boost(self):
        """Test that temporal boost is skipped when disabled."""
        from backend.src.rag.retriever import RAGRetriever

        mock_collection = MagicMock()
        mock_collection.query.return_value = {
            "documents": [["log entry"]],
            "metadatas": [[{"atm_id": "ATM-GB-0001", "last_timestamp": "2026-05-15T10:00:00Z"}]],
            "distances": [[0.3]],
            "ids": [["doc_1"]],
        }

        with patch.object(RAGRetriever, "_build_client", return_value=MagicMock()):
            with patch.object(RAGRetriever, "_get_collection", return_value=mock_collection):
                retriever = RAGRetriever()
                chunks = retriever.retrieve(query="test", temporal_boost=False)

        assert len(chunks) == 1