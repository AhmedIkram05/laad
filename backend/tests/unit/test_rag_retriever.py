"""Tests for RAG retriever module."""

from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.rag


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
                with patch.object(
                    RAGRetriever, "_get_collection", return_value=MagicMock()
                ):
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
            "metadatas": [
                [
                    {"atm_id": "ATM-GB-0001", "last_timestamp": "2026-05-15T10:00:00Z"},
                    {"atm_id": "ATM-GB-0002", "last_timestamp": "2026-05-15T10:01:00Z"},
                ]
            ],
            "distances": [[0.2, 0.3]],
            "ids": [["doc_1", "doc_2"]],
        }

        with patch.object(RAGRetriever, "_build_client", return_value=MagicMock()):
            with patch.object(
                RAGRetriever, "_get_collection", return_value=mock_collection
            ):
                retriever = RAGRetriever()
                chunks = retriever.retrieve(
                    query="test", top_k=2, temporal_boost=False, most_recent_first=False
                )

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
            with patch.object(
                RAGRetriever, "_get_collection", return_value=mock_collection
            ):
                retriever = RAGRetriever()
                chunks = retriever.retrieve(query="test")

        assert chunks == []

    def test_retrieve_by_atm(self):
        from backend.src.rag.retriever import RAGRetriever

        mock_collection = MagicMock()
        mock_collection.get.return_value = {
            "documents": ["log 1", "log 2"],
            "metadatas": [
                {"last_timestamp": "2026-05-15T10:00:00Z"},
                {"last_timestamp": "2026-05-15T10:01:00Z"},
            ],
            "ids": ["id_1", "id_2"],
        }

        with patch.object(RAGRetriever, "_build_client", return_value=MagicMock()):
            with patch.object(
                RAGRetriever, "_get_collection", return_value=mock_collection
            ):
                retriever = RAGRetriever()
                chunks = retriever.retrieve_by_atm(atm_id="ATM-GB-0001", limit=2)

        assert len(chunks) == 2
        assert chunks[0].atm_id == "ATM-GB-0001"

    def test_get_collection_stats(self):
        from backend.src.rag.retriever import RAGRetriever

        mock_collection = MagicMock()
        mock_collection.count.return_value = 100

        with patch.object(RAGRetriever, "_build_client", return_value=MagicMock()):
            with patch.object(
                RAGRetriever, "_get_collection", return_value=mock_collection
            ):
                retriever = RAGRetriever()
                stats = retriever.get_collection_stats()

        assert stats["total_chunks"] == 100

    def test_get_collection_stats_on_error(self):
        from backend.src.rag.retriever import RAGRetriever

        mock_collection = MagicMock()
        mock_collection.count.side_effect = Exception("Connection failed")

        with patch.object(RAGRetriever, "_build_client", return_value=MagicMock()):
            with patch.object(
                RAGRetriever, "_get_collection", return_value=mock_collection
            ):
                retriever = RAGRetriever()
                stats = retriever.get_collection_stats()

        assert "error" in stats

    def test_retrieve_with_anomaly_type_filter(self):
        """Test retrieval filtered by anomaly type."""
        from backend.src.rag.retriever import RAGRetriever

        mock_collection = MagicMock()
        mock_collection.query.return_value = {
            "documents": [["log entry with A1 tag"]],
            "metadatas": [
                [
                    {
                        "atm_id": "ATM-GB-0001",
                        "last_timestamp": "2026-05-15T10:00:00Z",
                        "_anomaly_tag": "A1",
                    }
                ]
            ],
            "distances": [[0.2]],
            "ids": [["doc_1"]],
        }

        with patch.object(RAGRetriever, "_build_client", return_value=MagicMock()):
            with patch.object(
                RAGRetriever, "_get_collection", return_value=mock_collection
            ):
                retriever = RAGRetriever()
                chunks = retriever.retrieve(
                    query="network timeout", anomaly_type="A1", error_only=False
                )

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
            "metadatas": [
                [{"atm_id": "ATM-GB-0001", "last_timestamp": "2026-05-15T10:00:00Z"}]
            ],
            "distances": [[0.3]],
            "ids": [["doc_1"]],
        }

        with patch.object(RAGRetriever, "_build_client", return_value=MagicMock()):
            with patch.object(
                RAGRetriever, "_get_collection", return_value=mock_collection
            ):
                retriever = RAGRetriever()
                _ = retriever.retrieve(
                    query="test",
                    atm_id="ATM-GB-0001",
                    anomaly_type="A3",
                    error_only=False,
                )

        call_kwargs = mock_collection.query.call_args[1]
        assert call_kwargs["where"] == {
            "$and": [{"atm_id": "ATM-GB-0001"}, {"_anomaly_tag": "A3"}]
        }

    def test_retrieve_with_temporal_boost(self):
        """Test that temporal boost is applied when enabled."""
        from backend.src.rag.retriever import RAGRetriever

        mock_collection = MagicMock()
        mock_collection.query.return_value = {
            "documents": [["recent log", "old log"]],
            "metadatas": [
                [
                    {"atm_id": "ATM-GB-0001", "last_timestamp": "2026-05-19T10:00:00Z"},
                    {"atm_id": "ATM-GB-0001", "last_timestamp": "2026-05-18T10:00:00Z"},
                ]
            ],
            "distances": [[0.5, 0.5]],
            "ids": [["doc_1", "doc_2"]],
        }

        with patch.object(RAGRetriever, "_build_client", return_value=MagicMock()):
            with patch.object(
                RAGRetriever, "_get_collection", return_value=mock_collection
            ):
                retriever = RAGRetriever()
                chunks = retriever.retrieve(query="test", temporal_boost=True)

        assert len(chunks) == 2

    def test_retrieve_without_temporal_boost(self):
        """Test that temporal boost is skipped when disabled."""
        from backend.src.rag.retriever import RAGRetriever

        mock_collection = MagicMock()
        mock_collection.query.return_value = {
            "documents": [["log entry"]],
            "metadatas": [
                [{"atm_id": "ATM-GB-0001", "last_timestamp": "2026-05-15T10:00:00Z"}]
            ],
            "distances": [[0.3]],
            "ids": [["doc_1"]],
        }

        with patch.object(RAGRetriever, "_build_client", return_value=MagicMock()):
            with patch.object(
                RAGRetriever, "_get_collection", return_value=mock_collection
            ):
                retriever = RAGRetriever()
                chunks = retriever.retrieve(query="test", temporal_boost=False)

        assert len(chunks) == 1

    def test_cross_encoder_graceful_degradation(self):
        """Test that missing sentence-transformers doesn't crash retrieval."""
        from backend.src.rag.retriever import RAGRetriever

        mock_collection = MagicMock()
        mock_collection.query.return_value = {
            "documents": [["log entry 1", "log entry 2"]],
            "metadatas": [
                [
                    {"atm_id": "ATM-GB-0001", "last_timestamp": "2026-05-15T10:00:00Z"},
                    {"atm_id": "ATM-GB-0002", "last_timestamp": "2026-05-15T10:01:00Z"},
                ]
            ],
            "distances": [[0.2, 0.3]],
            "ids": [["doc_1", "doc_2"]],
        }

        with patch.object(RAGRetriever, "_build_client", return_value=MagicMock()):
            with patch.object(
                RAGRetriever, "_get_collection", return_value=mock_collection
            ):
                with patch("backend.src.rag.retriever._HAS_CROSS_ENCODER", False):
                    retriever = RAGRetriever()
                    chunks = retriever.retrieve(
                        query="test", top_k=2, temporal_boost=False
                    )

        assert len(chunks) == 2
        assert retriever._cross_encoder is None

    def test_cross_encoder_skipped_when_disabled(self):
        """Test that cross-encoder is skipped when config disables it."""
        from backend.src.rag.retriever import RAGRetriever

        mock_collection = MagicMock()
        mock_collection.query.return_value = {
            "documents": [["log entry"]],
            "metadatas": [
                [{"atm_id": "ATM-GB-0001", "last_timestamp": "2026-05-15T10:00:00Z"}]
            ],
            "distances": [[0.3]],
            "ids": [["doc_1"]],
        }

        with patch.object(RAGRetriever, "_build_client", return_value=MagicMock()):
            with patch.object(
                RAGRetriever, "_get_collection", return_value=mock_collection
            ):
                with patch("backend.src.rag.retriever.config") as mock_config:
                    mock_config.cross_encoder_enabled = False
                    mock_config.retrieval_top_k = 3
                    mock_config.error_only = False
                    mock_config.most_recent_first = False
                    retriever = RAGRetriever()
                    chunks = retriever.retrieve(query="test")

        assert len(chunks) == 1


def _hybrid_test_retriever(mock_collection):
    from backend.src.rag.retriever import RAGRetriever

    retriever = RAGRetriever.__new__(RAGRetriever)
    retriever.client = MagicMock()
    retriever.collection = mock_collection
    retriever._cross_encoder = None
    retriever._sparse_cache = {}
    return retriever


class TestHybridRetrieval:
    """Tests for stdlib BM25+RRF hybrid fusion."""

    def test_bm25_scores_orders_relevant_first(self):
        from backend.src.rag.retriever import _bm25_scores, _tokenize

        query = _tokenize("atm cash dispenser error")
        docs = [
            _tokenize("atm cash dispenser error fault failure"),
            _tokenize("weather sunny picnic park"),
        ]
        scores = _bm25_scores(query, docs)
        assert scores[0] > scores[1]
        repeated = _bm25_scores(_tokenize("error error error"), docs)
        single = _bm25_scores(_tokenize("error"), docs)
        assert repeated == single

    def test_rrf_fuse_prefers_in_both(self):
        from backend.src.rag.retriever import _rrf_fuse

        fused = _rrf_fuse([["a", "b", "c"], ["c", "x", "y"]])
        assert fused[0] == "c"

    def test_hybrid_fallback_on_large_collection(self):
        from backend.src.rag.retriever import RetrievedChunk

        mock_collection = MagicMock()
        mock_collection.count.return_value = 6000
        retriever = _hybrid_test_retriever(mock_collection)
        dense = [
            RetrievedChunk(
                text="dense only",
                chunk_id="doc_1",
                atm_id="ATM-GB-0001",
                timestamp="2026-05-15T10:00:00Z",
                distance=0.2,
                confidence_score=0.8,
            )
        ]
        out = retriever._fuse_hybrid("test query", dense, None, 6)
        assert out == dense
        mock_collection.get.assert_not_called()

    def test_retrieve_enable_hybrid_false_legacy(self):
        from backend.src.rag.retriever import RAGRetriever

        mock_collection = MagicMock()
        mock_collection.query.return_value = {
            "documents": [["log entry"]],
            "metadatas": [
                [{"atm_id": "ATM-GB-0001", "last_timestamp": "2026-05-15T10:00:00Z"}]
            ],
            "distances": [[0.3]],
            "ids": [["doc_1"]],
        }
        retriever = _hybrid_test_retriever(mock_collection)
        with patch.object(RAGRetriever, "_fuse_hybrid") as mock_fuse:
            with patch("backend.src.rag.retriever.config") as mock_config:
                mock_config.cross_encoder_enabled = False
                mock_config.retrieval_top_k = 3
                mock_config.error_only = False
                mock_config.most_recent_first = False
                chunks = retriever.retrieve(
                    query="test",
                    top_k=1,
                    temporal_boost=False,
                    most_recent_first=False,
                    enable_hybrid=False,
                )
        mock_fuse.assert_not_called()
        assert len(chunks) == 1
        assert chunks[0].chunk_id == "doc_1"
        mock_collection.get.assert_not_called()


class _PoolCollection:
    """Fake Chroma collection with a mutable doc store and call recording."""

    def __init__(self, docs):
        import backend.src.rag.retriever as rt

        self.state = {"docs": dict(docs)}
        self.calls = []
        self._rt = rt

        def _get(ids=None, where=None, limit=None, offset=None, include=None, **_):
            self.calls.append({"ids": ids, "include": include, "limit": limit})
            chosen = list(ids) if ids is not None else list(self.state["docs"])
            out_ids, out_docs, out_metas = [], [], []
            for cid in chosen:
                if cid in self.state["docs"]:
                    out_ids.append(cid)
                    out_docs.append(self.state["docs"][cid])
                    out_metas.append({"atm_id": "ATM-GB-0001"})
            if include == []:
                return {"ids": out_ids}
            return {"ids": out_ids, "documents": out_docs, "metadatas": out_metas}

        self.get = MagicMock(side_effect=_get)
        self.count = MagicMock(return_value=len(docs))

    def full_fetch_calls(self):
        return [c for c in self.calls if c["include"]]


class TestSparsePoolCaching:
    """Audit finding #7: the sparse pool must not re-download/re-tokenize the
    collection per query; tokens are cached by doc id and BM25 stats ride on
    the cached pool."""

    @staticmethod
    def _dense(cid):
        from backend.src.rag.retriever import RetrievedChunk

        return RetrievedChunk(
            text=f"dense text {cid}",
            chunk_id=cid,
            atm_id="ATM-GB-0001",
            timestamp="2026-05-15T10:00:00Z",
            distance=0.2,
            confidence_score=0.8,
        )

    def test_second_call_does_not_refetch_or_retokenize(self, monkeypatch):
        import backend.src.rag.retriever as rt

        coll = _PoolCollection(
            {
                "s1": "atm cash dispenser jam",
                "s2": "weather sunny picnic park",
                "s3": "cash dispenser error fault",
            }
        )
        retriever = _hybrid_test_retriever(coll)
        real_tokenize = rt._tokenize
        seen = []

        def spy(text):
            seen.append(text)
            return real_tokenize(text)

        monkeypatch.setattr(rt, "_tokenize", spy)

        retriever._fuse_hybrid("cash error", [self._dense("s2")], None, 6)
        first_fetches = len(coll.full_fetch_calls())
        first_tokenizations = len(seen)

        retriever._fuse_hybrid("cash error", [self._dense("s2")], None, 6)

        assert len(coll.full_fetch_calls()) == first_fetches == 1
        assert len(seen) == first_tokenizations + 1  # only the query itself
        assert seen.count("atm cash dispenser jam") == 1
        assert seen.count("cash dispenser error fault") == 1

    def test_new_doc_tokenized_exactly_once(self, monkeypatch):
        import backend.src.rag.retriever as rt

        coll = _PoolCollection({"s1": "atm cash dispenser error"})
        retriever = _hybrid_test_retriever(coll)
        real_tokenize = rt._tokenize
        seen = []
        monkeypatch.setattr(
            rt, "_tokenize", lambda t: (seen.append(t), real_tokenize(t))[1]
        )

        retriever._fuse_hybrid("cash error", [self._dense("s1")], None, 6)
        retriever._fuse_hybrid("cash error", [self._dense("s1")], None, 6)

        coll.state["docs"]["s4"] = "cash dispenser fault jam"
        retriever._fuse_hybrid("cash error", [self._dense("s1")], None, 6)
        retriever._fuse_hybrid("cash error", [self._dense("s1")], None, 6)

        assert seen.count("cash dispenser fault jam") == 1
        # Two full fetches total: initial corpus + one for the new doc only.
        assert len(coll.full_fetch_calls()) == 2
        assert coll.full_fetch_calls()[1]["ids"] == ["s4"]

    def test_fetch_is_capped_with_limit(self):
        import backend.src.rag.retriever as rt

        coll = _PoolCollection({"s1": "atm error", "s2": "atm fault"})
        retriever = _hybrid_test_retriever(coll)
        retriever._fuse_hybrid("atm", [self._dense("s1")], None, 6)
        assert coll.calls, "expected collection.get calls"
        assert all(c["limit"] == rt._MAX_HYBRID_DOCS for c in coll.calls)

    def test_token_cache_is_size_capped(self):
        import backend.src.rag.retriever as rt

        coll = _PoolCollection({"s1": "atm error"})
        retriever = _hybrid_test_retriever(coll)
        retriever._sparse_pool(None)  # initializes caches
        retriever._token_cache = {f"filler_{i}": [] for i in range(rt._TOKEN_CACHE_MAX)}

        retriever._tokens_for("new_doc", "hello world")

        assert len(retriever._token_cache) == rt._TOKEN_CACHE_MAX
        assert "new_doc" in retriever._token_cache

    def test_vanished_doc_token_entry_dropped(self):
        coll = _PoolCollection({"s1": "atm error", "s3": "unrelated text"})
        retriever = _hybrid_test_retriever(coll)
        retriever._fuse_hybrid("atm", [self._dense("s1")], None, 6)
        assert "s3" in retriever._token_cache

        del coll.state["docs"]["s3"]
        retriever._fuse_hybrid("atm", [self._dense("s1")], None, 6)

        assert "s3" not in retriever._token_cache
        assert "s1" in retriever._token_cache

    def test_ordering_matches_uncompressed_bm25_rrf_path(self):
        import heapq

        import backend.src.rag.retriever as rt

        corpus = {
            "s1": "atm cash dispenser jam error",
            "s2": "cash dispenser error fault failure",
            "s3": "weather sunny picnic park",
            "s4": "atm error screen fault",
        }
        coll = _PoolCollection(corpus)
        retriever = _hybrid_test_retriever(coll)
        query = "cash dispenser error"
        dense = [self._dense("s2"), self._dense("s3")]

        out = retriever._fuse_hybrid(query, dense, None, 6)

        # Oracle: the original uncompressed path — BM25 over the raw pool
        # tokens, RRF fusion against the dense ranking.
        pool_ids = list(corpus)
        scores = rt._bm25_scores(
            rt._tokenize(query), [rt._tokenize(corpus[cid]) for cid in pool_ids]
        )
        top = heapq.nlargest(6, range(len(scores)), key=scores.__getitem__)
        sparse_ids = [pool_ids[i] for i in top if scores[i] > 0]
        fused = rt._rrf_scores([["s2", "s3"], sparse_ids])
        expected_order = sorted(fused, key=lambda c: fused[c], reverse=True)

        assert [c.chunk_id for c in out] == expected_order
        assert "s1" in [c.chunk_id for c in out]  # sparse-only hit surfaced
