"""Coverage tests for backend.src.rag.retriever."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.rag


class TestClearCollection:
    """Test clear_collection method."""

    def test_clear_collection_success(self):
        """Happy path: deletes and recreates collection."""
        from backend.src.rag.retriever import RAGRetriever

        mock_client = MagicMock()
        mock_new_collection = MagicMock()
        mock_client.create_collection.return_value = mock_new_collection

        with (
            patch.object(RAGRetriever, "_build_client", return_value=mock_client),
            patch.object(RAGRetriever, "_get_collection", return_value=MagicMock()),
        ):
            retriever = RAGRetriever()

        result = retriever.clear_collection()

        assert result["success"] is True
        assert "Cleared collection" in result["message"]
        mock_client.delete_collection.assert_called_once()
        mock_client.create_collection.assert_called_once()

    def test_clear_collection_chromadb_unavailable(self):
        """Returns error when client is None."""
        from backend.src.rag.retriever import RAGRetriever

        with (
            patch.object(RAGRetriever, "_build_client", return_value=MagicMock()),
            patch.object(RAGRetriever, "_get_collection", return_value=MagicMock()),
        ):
            retriever = RAGRetriever()

        retriever.client = None
        retriever.collection = None

        result = retriever.clear_collection()
        assert "error" in result
        assert "ChromaDB unavailable" in result["error"]

    def test_clear_collection_exception(self):
        """Exception during delete is caught."""
        from backend.src.rag.retriever import RAGRetriever

        mock_client = MagicMock()
        mock_client.delete_collection.side_effect = Exception("delete failed")

        with (
            patch.object(RAGRetriever, "_build_client", return_value=mock_client),
            patch.object(RAGRetriever, "_get_collection", return_value=MagicMock()),
        ):
            retriever = RAGRetriever()

        result = retriever.clear_collection()
        assert "error" in result
        assert "delete failed" in result["error"]


class TestRebuildCollection:
    """Test rebuild_collection method."""

    def test_rebuild_collection_success(self):
        """Happy path: deletes and recreates without new client."""
        from backend.src.rag.retriever import RAGRetriever

        mock_client = MagicMock()
        mock_new_collection = MagicMock()
        mock_client.create_collection.return_value = mock_new_collection

        with (
            patch.object(RAGRetriever, "_build_client", return_value=mock_client),
            patch.object(RAGRetriever, "_get_collection", return_value=MagicMock()),
        ):
            retriever = RAGRetriever()

        result = retriever.rebuild_collection(new_client=False)

        assert result["success"] is True
        assert "Rebuilt collection" in result["message"]
        mock_client.delete_collection.assert_called_once()
        mock_client.create_collection.assert_called_once()

    def test_rebuild_collection_with_new_client(self):
        """Rebuilds with new client when new_client=True."""
        from backend.src.rag.retriever import RAGRetriever

        old_client = MagicMock()
        new_client = MagicMock()
        mock_new_collection = MagicMock()
        new_client.create_collection.return_value = mock_new_collection

        with (
            patch.object(RAGRetriever, "_build_client", return_value=old_client),
            patch.object(RAGRetriever, "_get_collection", return_value=MagicMock()),
        ):
            retriever = RAGRetriever()

        with patch.object(retriever, "_build_client", return_value=new_client):
            result = retriever.rebuild_collection(new_client=True)

        assert result["success"] is True
        new_client.delete_collection.assert_called_once()
        new_client.create_collection.assert_called_once()

    def test_rebuild_collection_chromadb_unavailable(self):
        """Returns error when client is None."""
        from backend.src.rag.retriever import RAGRetriever

        with (
            patch.object(RAGRetriever, "_build_client", return_value=MagicMock()),
            patch.object(RAGRetriever, "_get_collection", return_value=MagicMock()),
        ):
            retriever = RAGRetriever()

        retriever.client = None

        result = retriever.rebuild_collection()
        assert "error" in result
        assert "ChromaDB unavailable" in result["error"]

    def test_rebuild_collection_exception(self):
        """Exception during rebuild is caught."""
        from backend.src.rag.retriever import RAGRetriever

        mock_client = MagicMock()
        mock_client.delete_collection.side_effect = Exception("rebuild failed")

        with (
            patch.object(RAGRetriever, "_build_client", return_value=mock_client),
            patch.object(RAGRetriever, "_get_collection", return_value=MagicMock()),
        ):
            retriever = RAGRetriever()

        result = retriever.rebuild_collection()
        assert "error" in result
        assert "rebuild failed" in result["error"]


class TestResetRetriever:
    """Test the module-level reset_retriever function."""

    def test_reset_sets_singleton_to_none(self):
        """reset_retriever sets the global _retriever to None."""
        import backend.src.rag.retriever as mod

        original = mod._retriever
        try:
            mod._retriever = MagicMock()
            mod.reset_retriever()
            assert mod._retriever is None
        finally:
            mod._retriever = original

    def test_get_retriever_creates_new_after_reset(self):
        """get_retriever creates a new instance after reset."""
        import backend.src.rag.retriever as mod

        original = mod._retriever
        try:
            mod._retriever = MagicMock()
            mod.reset_retriever()

            mock_client = MagicMock()
            mock_collection = MagicMock()
            with (
                patch.object(
                    mod.RAGRetriever, "_build_client", return_value=mock_client
                ),
                patch.object(
                    mod.RAGRetriever, "_get_collection", return_value=mock_collection
                ),
            ):
                retriever = mod.get_retriever()
                assert retriever is not None
        finally:
            mod._retriever = original


class TestSortByMostRecent:
    """Test _sort_by_most_recent method."""

    def test_sorts_descending_by_timestamp(self):
        """Most recent timestamps come first."""
        from backend.src.rag.retriever import RAGRetriever, RetrievedChunk

        retriever = RAGRetriever.__new__(RAGRetriever)
        chunks = [
            RetrievedChunk(
                text="old",
                chunk_id="1",
                atm_id="ATM-1",
                timestamp="2026-01-01T10:00:00Z",
                distance=0.1,
                confidence_score=0.9,
            ),
            RetrievedChunk(
                text="new",
                chunk_id="2",
                atm_id="ATM-1",
                timestamp="2026-06-01T10:00:00Z",
                distance=0.1,
                confidence_score=0.9,
            ),
            RetrievedChunk(
                text="mid",
                chunk_id="3",
                atm_id="ATM-1",
                timestamp="2026-03-01T10:00:00Z",
                distance=0.1,
                confidence_score=0.9,
            ),
        ]

        sorted_chunks = retriever._sort_by_most_recent(chunks)

        assert sorted_chunks[0].text == "new"
        assert sorted_chunks[1].text == "mid"
        assert sorted_chunks[2].text == "old"

    def test_chunks_without_timestamps_at_end(self):
        """Chunks with None timestamps are placed at the end."""
        from backend.src.rag.retriever import RAGRetriever, RetrievedChunk

        retriever = RAGRetriever.__new__(RAGRetriever)
        chunks = [
            RetrievedChunk(
                text="no_ts",
                chunk_id="1",
                atm_id="ATM-1",
                timestamp=None,
                distance=0.1,
                confidence_score=0.9,
            ),
            RetrievedChunk(
                text="has_ts",
                chunk_id="2",
                atm_id="ATM-1",
                timestamp="2026-06-01T10:00:00Z",
                distance=0.1,
                confidence_score=0.9,
            ),
        ]

        sorted_chunks = retriever._sort_by_most_recent(chunks)

        assert sorted_chunks[0].text == "has_ts"
        assert sorted_chunks[1].text == "no_ts"

    def test_invalid_timestamp_format_goes_to_end(self):
        """Chunks with unparseable timestamps are placed at end."""
        from backend.src.rag.retriever import RAGRetriever, RetrievedChunk

        retriever = RAGRetriever.__new__(RAGRetriever)
        chunks = [
            RetrievedChunk(
                text="invalid_ts",
                chunk_id="1",
                atm_id="ATM-1",
                timestamp="not-a-date",
                distance=0.1,
                confidence_score=0.9,
            ),
            RetrievedChunk(
                text="valid_ts",
                chunk_id="2",
                atm_id="ATM-1",
                timestamp="2026-06-01T10:00:00Z",
                distance=0.1,
                confidence_score=0.9,
            ),
        ]

        sorted_chunks = retriever._sort_by_most_recent(chunks)

        assert sorted_chunks[0].text == "valid_ts"
        assert sorted_chunks[1].text == "invalid_ts"

    def test_empty_list(self):
        """Empty list returns empty list."""
        from backend.src.rag.retriever import RAGRetriever

        retriever = RAGRetriever.__new__(RAGRetriever)
        assert retriever._sort_by_most_recent([]) == []


class TestRetrieveErrorOnlyFilter:
    """Test retrieve with error_only=True filter."""

    def test_error_only_builds_correct_filter(self):
        """error_only=True creates severity/or filter."""
        from backend.src.rag.retriever import RAGRetriever

        mock_collection = MagicMock()
        mock_collection.query.return_value = {
            "documents": [],
            "metadatas": [],
            "distances": [],
            "ids": [],
        }

        with (
            patch.object(RAGRetriever, "_build_client", return_value=MagicMock()),
            patch.object(RAGRetriever, "_get_collection", return_value=mock_collection),
            patch("backend.src.rag.retriever.config") as mock_config,
        ):
            mock_config.retrieval_top_k = 5
            mock_config.error_only = False
            mock_config.most_recent_first = False
            mock_config.cross_encoder_enabled = False
            mock_config.anomaly_types = ["A1", "A2", "A3"]

            retriever = RAGRetriever()
            retriever.retrieve(query="test", error_only=True)

        call_kwargs = mock_collection.query.call_args[1]
        where_filter = call_kwargs["where"]
        assert "$or" in where_filter
        assert {"severity": "ERROR"} in where_filter["$or"]
        assert {"severity": "FATAL"} in where_filter["$or"]


class TestRetrieveCollectionNone:
    """Test retrieve when collection is None."""

    def test_returns_empty_list(self):
        """No crash when collection is None."""
        from backend.src.rag.retriever import RAGRetriever

        with (
            patch.object(RAGRetriever, "_build_client", return_value=MagicMock()),
            patch.object(RAGRetriever, "_get_collection", return_value=MagicMock()),
        ):
            retriever = RAGRetriever()

        retriever.collection = None

        result = retriever.retrieve(query="test")
        assert result == []


class TestInitChromaDBFailure:
    """Test __init__ when ChromaDB client creation fails."""

    def test_client_none_on_exception(self):
        """Sets client and collection to None when _build_client raises."""
        from backend.src.rag.retriever import RAGRetriever

        with patch.object(
            RAGRetriever, "_build_client", side_effect=Exception("conn refused")
        ):
            retriever = RAGRetriever()

        assert retriever.client is None
        assert retriever.collection is None
        assert retriever._cross_encoder is None


class TestLoadCrossEncoder:
    """Test _load_cross_encoder method."""

    def test_load_cross_encoder_success(self):
        """Happy path: loads CrossEncoder successfully."""
        import backend.src.rag.retriever as mod
        from backend.src.rag.retriever import RAGRetriever

        retriever = RAGRetriever.__new__(RAGRetriever)
        retriever._cross_encoder = None
        mock_ce_class = MagicMock()
        mock_ce_instance = MagicMock()
        mock_ce_class.return_value = mock_ce_instance

        with (
            patch("backend.src.rag.retriever._HAS_CROSS_ENCODER", True),
            patch("backend.src.rag.retriever.config") as mock_config,
        ):
            mock_config.cross_encoder_enabled = True
            mock_config.cross_encoder_model = "test-model"
            # CrossEncoder is conditionally imported; inject it into module namespace
            setattr(mod, "CrossEncoder", mock_ce_class)
            try:
                retriever._load_cross_encoder()
            finally:
                delattr(mod, "CrossEncoder")

        assert retriever._cross_encoder is mock_ce_instance
        mock_ce_class.assert_called_once_with("test-model")

    def test_load_cross_encoder_already_loaded(self):
        """Returns early if cross encoder already loaded."""
        from backend.src.rag.retriever import RAGRetriever

        retriever = RAGRetriever.__new__(RAGRetriever)
        retriever._cross_encoder = MagicMock()

        retriever._load_cross_encoder()
        # Should not raise, should return early
        assert retriever._cross_encoder is not None

    def test_load_cross_encoder_no_module(self):
        """Returns early when _HAS_CROSS_ENCODER is False."""
        from backend.src.rag.retriever import RAGRetriever

        retriever = RAGRetriever.__new__(RAGRetriever)
        retriever._cross_encoder = None

        with patch("backend.src.rag.retriever._HAS_CROSS_ENCODER", False):
            retriever._load_cross_encoder()

        assert retriever._cross_encoder is None

    def test_load_cross_encoder_disabled_by_config(self):
        """Returns early when cross_encoder_enabled is False."""
        from backend.src.rag.retriever import RAGRetriever

        retriever = RAGRetriever.__new__(RAGRetriever)
        retriever._cross_encoder = None

        with (
            patch("backend.src.rag.retriever._HAS_CROSS_ENCODER", True),
            patch("backend.src.rag.retriever.config") as mock_config,
        ):
            mock_config.cross_encoder_enabled = False
            retriever._load_cross_encoder()

        assert retriever._cross_encoder is None

    def test_load_cross_encoder_exception_during_load(self):
        """Exception during model load is caught, cross_encoder stays None."""
        import backend.src.rag.retriever as mod
        from backend.src.rag.retriever import RAGRetriever

        retriever = RAGRetriever.__new__(RAGRetriever)
        retriever._cross_encoder = None

        failing_ce = MagicMock(side_effect=Exception("model download failed"))

        with (
            patch("backend.src.rag.retriever._HAS_CROSS_ENCODER", True),
            patch("backend.src.rag.retriever.config") as mock_config,
        ):
            mock_config.cross_encoder_enabled = True
            mock_config.cross_encoder_model = "bad-model"
            # CrossEncoder is conditionally imported; inject failing version
            setattr(mod, "CrossEncoder", failing_ce)
            try:
                retriever._load_cross_encoder()
            finally:
                delattr(mod, "CrossEncoder")

        assert retriever._cross_encoder is None


class TestRerankWithCrossEncoder:
    """Test _rerank_with_cross_encoder method."""

    def test_rerank_returns_original_when_no_encoder(self):
        """Returns original chunks when cross_encoder is None."""
        from backend.src.rag.retriever import RAGRetriever, RetrievedChunk

        retriever = RAGRetriever.__new__(RAGRetriever)
        retriever._cross_encoder = None
        chunks = [
            RetrievedChunk(
                text="text",
                chunk_id="1",
                atm_id="ATM-1",
                timestamp="2026-06-01T10:00:00Z",
                distance=0.3,
                confidence_score=0.7,
            )
        ]

        result = retriever._rerank_with_cross_encoder("query", chunks)
        assert result is chunks

    def test_rerank_applies_ce_scores(self):
        """Reranking updates distances and sorts by CE score."""
        from backend.src.rag.retriever import RAGRetriever, RetrievedChunk

        retriever = RAGRetriever.__new__(RAGRetriever)
        mock_ce = MagicMock()
        mock_ce.predict.return_value = [0.9, 0.3]  # first chunk gets higher CE score
        retriever._cross_encoder = mock_ce

        chunks = [
            RetrievedChunk(
                text="low relevance",
                chunk_id="1",
                atm_id="ATM-1",
                timestamp=None,
                distance=0.3,
                confidence_score=0.7,
            ),
            RetrievedChunk(
                text="high relevance",
                chunk_id="2",
                atm_id="ATM-1",
                timestamp=None,
                distance=0.3,
                confidence_score=0.7,
            ),
        ]

        result = retriever._rerank_with_cross_encoder("query", chunks)

        assert len(result) == 2
        # After reranking, chunks sorted by distance ascending (lower = more relevant)
        # CE score 0.9 -> distance = max(0, 1-0.9) = 0.1
        # CE score 0.3 -> distance = max(0, 1-0.3) = 0.7
        assert result[0].distance <= result[1].distance

    def test_rerank_exception_returns_original_order(self):
        """Exception from CE predict returns original order."""
        from backend.src.rag.retriever import RAGRetriever, RetrievedChunk

        retriever = RAGRetriever.__new__(RAGRetriever)
        mock_ce = MagicMock()
        mock_ce.predict.side_effect = Exception("predict failed")
        retriever._cross_encoder = mock_ce

        chunks = [
            RetrievedChunk(
                text="a",
                chunk_id="1",
                atm_id="ATM-1",
                timestamp=None,
                distance=0.3,
                confidence_score=0.7,
            ),
        ]

        result = retriever._rerank_with_cross_encoder("query", chunks)
        assert result is chunks


class TestApplyTemporalBoost:
    """Test _apply_temporal_boost edge cases."""

    def test_boost_with_z_suffix_timestamp(self):
        """Handles 'Z' suffix in timestamp strings."""
        from backend.src.rag.retriever import RAGRetriever, RetrievedChunk

        retriever = RAGRetriever.__new__(RAGRetriever)
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        recent_ts = now.strftime("%Y-%m-%dT%H:%M:%SZ")

        chunks = [
            RetrievedChunk(
                text="recent",
                chunk_id="1",
                atm_id="ATM-1",
                timestamp=recent_ts,
                distance=0.5,
                confidence_score=0.5,
            ),
        ]

        result = retriever._apply_temporal_boost(chunks)
        assert len(result) == 1
        assert result[0].distance <= 0.5

    def test_boost_with_no_timestamp(self):
        """Chunks without timestamps keep original distance."""
        from backend.src.rag.retriever import RAGRetriever, RetrievedChunk

        retriever = RAGRetriever.__new__(RAGRetriever)
        chunks = [
            RetrievedChunk(
                text="no_ts",
                chunk_id="1",
                atm_id="ATM-1",
                timestamp=None,
                distance=0.5,
                confidence_score=0.5,
            ),
        ]

        result = retriever._apply_temporal_boost(chunks)
        assert len(result) == 1
        assert result[0].distance == 0.5

    def test_boost_with_invalid_timestamp(self):
        """Invalid timestamp format is silently skipped."""
        from backend.src.rag.retriever import RAGRetriever, RetrievedChunk

        retriever = RAGRetriever.__new__(RAGRetriever)
        chunks = [
            RetrievedChunk(
                text="bad_ts",
                chunk_id="1",
                atm_id="ATM-1",
                timestamp="not-a-date",
                distance=0.5,
                confidence_score=0.5,
            ),
        ]

        result = retriever._apply_temporal_boost(chunks)
        assert len(result) == 1
        assert result[0].distance == 0.5

    def test_boost_with_numeric_timestamp(self):
        """Handles numeric (float) timestamps."""
        from backend.src.rag.retriever import RAGRetriever, RetrievedChunk

        retriever = RAGRetriever.__new__(RAGRetriever)
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        numeric_ts = str(now.timestamp())

        chunks = [
            RetrievedChunk(
                text="num_ts",
                chunk_id="1",
                atm_id="ATM-1",
                timestamp=numeric_ts,
                distance=0.5,
                confidence_score=0.5,
            ),
        ]

        result = retriever._apply_temporal_boost(chunks)
        assert len(result) == 1
        assert result[0].distance <= 0.5

    def test_old_chunks_not_boosted(self):
        """Chunks older than 6 hours get no temporal boost."""
        from backend.src.rag.retriever import RAGRetriever, RetrievedChunk

        retriever = RAGRetriever.__new__(RAGRetriever)
        old_ts = "2020-01-01T10:00:00Z"
        chunks = [
            RetrievedChunk(
                text="old",
                chunk_id="1",
                atm_id="ATM-1",
                timestamp=old_ts,
                distance=0.5,
                confidence_score=0.5,
            ),
        ]

        result = retriever._apply_temporal_boost(chunks)
        assert len(result) == 1
        assert result[0].distance == 0.5


class TestRetrieveByAtmEdgeCases:
    """Test retrieve_by_atm edge cases."""

    def test_collection_none_returns_empty(self):
        """Returns empty when collection is None."""
        from backend.src.rag.retriever import RAGRetriever

        with (
            patch.object(RAGRetriever, "_build_client", return_value=MagicMock()),
            patch.object(RAGRetriever, "_get_collection", return_value=MagicMock()),
        ):
            retriever = RAGRetriever()

        retriever.collection = None
        result = retriever.retrieve_by_atm(atm_id="ATM-1")
        assert result == []

    def test_exception_during_get_returns_empty(self):
        """Exception from collection.get returns empty."""
        from backend.src.rag.retriever import RAGRetriever

        mock_collection = MagicMock()
        mock_collection.get.side_effect = Exception("timeout")

        with (
            patch.object(RAGRetriever, "_build_client", return_value=MagicMock()),
            patch.object(RAGRetriever, "_get_collection", return_value=mock_collection),
        ):
            retriever = RAGRetriever()

        result = retriever.retrieve_by_atm(atm_id="ATM-1")
        assert result == []


class TestGetCollectionStatsEdgeCases:
    """Test get_collection_stats edge cases."""

    def test_collection_none_returns_error(self):
        """Returns error when collection is None."""
        from backend.src.rag.retriever import RAGRetriever

        with (
            patch.object(RAGRetriever, "_build_client", return_value=MagicMock()),
            patch.object(RAGRetriever, "_get_collection", return_value=MagicMock()),
        ):
            retriever = RAGRetriever()

        retriever.collection = None
        stats = retriever.get_collection_stats()
        assert stats["error"] == "ChromaDB unavailable"
