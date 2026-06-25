"""Coverage tests for backend.src.rag.rag_pipeline."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


def _make_mock_chunks(n=1):
    """Create n mock RetrievedChunk objects."""
    return [
        MagicMock(
            text=f"Chunk {i}",
            chunk_id=f"c{i}",
            atm_id=f"ATM-{i:03d}",
            timestamp=f"2026-03-05T09:0{i}:00Z",
            confidence_score=0.8 + i * 0.05,
        )
        for i in range(1, n + 1)
    ]


def _make_mock_response(chunks=None):
    """Create a mock GeneratedResponse."""
    if chunks is None:
        chunks = _make_mock_chunks(1)
    resp = MagicMock()
    resp.text = "Generated answer"
    resp.model = "test-model"
    resp.sources = chunks
    resp.self_consistency_score = 0.95
    resp.verbalized_confidence = 0.9
    resp.grounding_score = 0.85
    resp.cross_encoder_used = True
    resp.was_revised = False
    return resp


def _make_mock_uncertainty(final_confidence=0.85, is_uncertain=False):
    """Create a mock UncertaintyEstimate."""
    est = MagicMock()
    est.final_confidence = final_confidence
    est.confidence_level = "high"
    est.is_uncertain = is_uncertain
    est.recommendation = "Auto-respond - high confidence in answer quality"
    est.generation_variance = 0.05
    return est


class TestProcessQuerySuccess:
    """Test successful RAG pipeline processing."""

    def test_success_path_with_uncertainty(self):
        """Full success with include_uncertainty=True."""
        from backend.src.rag.rag_pipeline import process_query

        mock_chunks = _make_mock_chunks(2)
        mock_retriever = MagicMock()
        mock_retriever.retrieve.return_value = mock_chunks

        mock_generator = MagicMock()
        mock_generator.generate.return_value = _make_mock_response(mock_chunks)

        mock_uncertainty = MagicMock()
        mock_uncertainty.estimate.return_value = _make_mock_uncertainty()

        with (
            patch(
                "backend.src.rag.rag_pipeline.get_retriever",
                return_value=mock_retriever,
            ),
            patch(
                "backend.src.rag.rag_pipeline.get_generator",
                return_value=mock_generator,
            ),
            patch(
                "backend.src.rag.rag_pipeline.get_uncertainty_estimator",
                return_value=mock_uncertainty,
            ),
        ):
            result = process_query(
                "test query", atm_id="ATM-001", top_k=3, include_uncertainty=True
            )

        assert result["answer"] == "Generated answer"
        assert result["model_used"] == "test-model"
        assert result["uncertainty_score"] == 0.85
        assert result["confidence_level"] == "high"
        assert result["is_uncertain"] is False
        assert (
            result["recommendation"]
            == "Auto-respond - high confidence in answer quality"
        )
        assert result["generation_variance"] == 0.05
        assert result["self_consistency_score"] == 0.95
        assert result["verbalized_confidence"] == 0.9
        assert result["grounding_score"] == 0.85
        assert result["cross_encoder_used"] is True
        assert result["was_revised"] is False
        assert len(result["sources"]) == 2
        assert result["sources"][0]["chunk_id"] == "c1"
        assert result["sources"][1]["chunk_id"] == "c2"
        mock_uncertainty.estimate.assert_called_once_with(
            query="test query",
            chunks=mock_chunks,
            self_consistency_score=0.95,
            verbalized_confidence=0.9,
            grounding_score=0.85,
        )

    def test_success_path_without_uncertainty(self):
        """Full success with include_uncertainty=False."""
        from backend.src.rag.rag_pipeline import process_query

        mock_chunks = _make_mock_chunks(1)
        mock_retriever = MagicMock()
        mock_retriever.retrieve.return_value = mock_chunks

        mock_generator = MagicMock()
        mock_generator.generate.return_value = _make_mock_response(mock_chunks)

        mock_uncertainty = MagicMock()

        with (
            patch(
                "backend.src.rag.rag_pipeline.get_retriever",
                return_value=mock_retriever,
            ),
            patch(
                "backend.src.rag.rag_pipeline.get_generator",
                return_value=mock_generator,
            ),
            patch(
                "backend.src.rag.rag_pipeline.get_uncertainty_estimator",
                return_value=mock_uncertainty,
            ),
        ):
            result = process_query("test query", include_uncertainty=False)

        assert result["answer"] == "Generated answer"
        assert result["uncertainty_score"] == 0.5
        assert result["confidence_level"] == "medium"
        assert result["is_uncertain"] is False
        assert result["recommendation"] == "Review recommended"
        assert result["generation_variance"] is None
        mock_uncertainty.estimate.assert_not_called()

    def test_passes_reflexion_params(self):
        """All passthrough params reach the generator."""
        from backend.src.rag.rag_pipeline import process_query

        mock_chunks = _make_mock_chunks(1)
        mock_retriever = MagicMock()
        mock_retriever.retrieve.return_value = mock_chunks

        mock_generator = MagicMock()
        mock_generator.generate.return_value = _make_mock_response(mock_chunks)

        mock_uncertainty = MagicMock()
        mock_uncertainty.estimate.return_value = _make_mock_uncertainty()

        with (
            patch(
                "backend.src.rag.rag_pipeline.get_retriever",
                return_value=mock_retriever,
            ),
            patch(
                "backend.src.rag.rag_pipeline.get_generator",
                return_value=mock_generator,
            ),
            patch(
                "backend.src.rag.rag_pipeline.get_uncertainty_estimator",
                return_value=mock_uncertainty,
            ),
        ):
            result = process_query(
                "test query",
                enable_reflexion=True,
                enable_citation_grounding=False,
                enable_self_consistency=True,
            )

        mock_generator.generate.assert_called_once_with(
            query="test query",
            chunks=mock_chunks,
            enable_reflexion=True,
            enable_citation_grounding=False,
            enable_self_consistency=True,
        )
        assert result["answer"] == "Generated answer"

    def test_default_params(self):
        """Default values for optional params work correctly."""
        from backend.src.rag.rag_pipeline import process_query

        mock_chunks = _make_mock_chunks(1)
        mock_retriever = MagicMock()
        mock_retriever.retrieve.return_value = mock_chunks

        mock_generator = MagicMock()
        mock_generator.generate.return_value = _make_mock_response(mock_chunks)

        mock_uncertainty = MagicMock()
        mock_uncertainty.estimate.return_value = _make_mock_uncertainty()

        with (
            patch(
                "backend.src.rag.rag_pipeline.get_retriever",
                return_value=mock_retriever,
            ),
            patch(
                "backend.src.rag.rag_pipeline.get_generator",
                return_value=mock_generator,
            ),
            patch(
                "backend.src.rag.rag_pipeline.get_uncertainty_estimator",
                return_value=mock_uncertainty,
            ),
        ):
            result = process_query("test query")

        mock_retriever.retrieve.assert_called_once_with(
            query="test query", atm_id=None, top_k=3
        )
        mock_generator.generate.assert_called_once_with(
            query="test query",
            chunks=mock_chunks,
            enable_reflexion=None,
            enable_citation_grounding=None,
            enable_self_consistency=None,
        )
        assert result["answer"] == "Generated answer"

    def test_sources_list_construction(self):
        """Sources list has correct fields from response."""
        from backend.src.rag.rag_pipeline import process_query

        chunk = MagicMock(
            text="log text",
            chunk_id="c42",
            atm_id="ATM-999",
            timestamp="2026-06-01T12:00:00Z",
            confidence_score=0.92,
        )
        mock_retriever = MagicMock()
        mock_retriever.retrieve.return_value = [chunk]

        mock_generator = MagicMock()
        resp = _make_mock_response([chunk])
        mock_generator.generate.return_value = resp

        mock_uncertainty = MagicMock()
        mock_uncertainty.estimate.return_value = _make_mock_uncertainty()

        with (
            patch(
                "backend.src.rag.rag_pipeline.get_retriever",
                return_value=mock_retriever,
            ),
            patch(
                "backend.src.rag.rag_pipeline.get_generator",
                return_value=mock_generator,
            ),
            patch(
                "backend.src.rag.rag_pipeline.get_uncertainty_estimator",
                return_value=mock_uncertainty,
            ),
        ):
            result = process_query("q", include_uncertainty=True)

        src = result["sources"][0]
        assert src["text"] == "log text"
        assert src["chunk_id"] == "c42"
        assert src["atm_id"] == "ATM-999"
        assert src["timestamp"] == "2026-06-01T12:00:00Z"
        assert src["confidence_score"] == 0.92


class TestProcessQueryNoChunks:
    """Test pipeline when retriever returns empty list."""

    def test_no_chunks_returns_error(self):
        """Empty chunk list returns error dict without calling generator."""
        from backend.src.rag.rag_pipeline import process_query

        mock_retriever = MagicMock()
        mock_retriever.retrieve.return_value = []

        mock_generator = MagicMock()
        mock_uncertainty = MagicMock()

        with (
            patch(
                "backend.src.rag.rag_pipeline.get_retriever",
                return_value=mock_retriever,
            ),
            patch(
                "backend.src.rag.rag_pipeline.get_generator",
                return_value=mock_generator,
            ),
            patch(
                "backend.src.rag.rag_pipeline.get_uncertainty_estimator",
                return_value=mock_uncertainty,
            ),
        ):
            result = process_query("no results query")

        assert result["error"] == "No relevant logs found"
        assert (
            result["answer"] == "I couldn't find any relevant log data for your query."
        )
        mock_generator.generate.assert_not_called()
        mock_uncertainty.estimate.assert_not_called()


class TestProcessQueryErrors:
    """Test pipeline error handling."""

    def test_retriever_exception_returns_fallback(self):
        """Exception from retriever returns error dict."""
        from backend.src.rag.rag_pipeline import process_query

        with (
            patch(
                "backend.src.rag.rag_pipeline.get_retriever",
                side_effect=Exception("DB connection lost"),
            ),
            patch("backend.src.rag.rag_pipeline.get_generator"),
            patch("backend.src.rag.rag_pipeline.get_uncertainty_estimator"),
        ):
            result = process_query("query")

        assert "error" in result
        assert "DB connection lost" in result["error"]
        assert result["answer"] == "I encountered an error processing your request."

    def test_generator_exception_returns_fallback(self):
        """Exception from generator returns error dict."""
        from backend.src.rag.rag_pipeline import process_query

        mock_retriever = MagicMock()
        mock_retriever.retrieve.return_value = _make_mock_chunks(1)

        mock_generator = MagicMock()
        mock_generator.generate.side_effect = Exception("LLM timeout")

        with (
            patch(
                "backend.src.rag.rag_pipeline.get_retriever",
                return_value=mock_retriever,
            ),
            patch(
                "backend.src.rag.rag_pipeline.get_generator",
                return_value=mock_generator,
            ),
            patch("backend.src.rag.rag_pipeline.get_uncertainty_estimator"),
        ):
            result = process_query("query")

        assert "error" in result
        assert "LLM timeout" in result["error"]
        assert result["answer"] == "I encountered an error processing your request."

    def test_uncertainty_estimator_exception_returns_fallback(self):
        """Exception from uncertainty estimator returns error dict."""
        from backend.src.rag.rag_pipeline import process_query

        mock_retriever = MagicMock()
        mock_retriever.retrieve.return_value = _make_mock_chunks(1)

        mock_generator = MagicMock()
        mock_generator.generate.return_value = _make_mock_response()

        mock_uncertainty = MagicMock()
        mock_uncertainty.estimate.side_effect = Exception("Estimator crashed")

        with (
            patch(
                "backend.src.rag.rag_pipeline.get_retriever",
                return_value=mock_retriever,
            ),
            patch(
                "backend.src.rag.rag_pipeline.get_generator",
                return_value=mock_generator,
            ),
            patch(
                "backend.src.rag.rag_pipeline.get_uncertainty_estimator",
                return_value=mock_uncertainty,
            ),
        ):
            result = process_query("query", include_uncertainty=True)

        assert "error" in result
        assert "Estimator crashed" in result["error"]
        assert result["answer"] == "I encountered an error processing your request."

    def test_retriever_raises_type_error(self):
        """Non-Exception BaseException subclass is also caught."""
        from backend.src.rag.rag_pipeline import process_query

        with (
            patch(
                "backend.src.rag.rag_pipeline.get_retriever",
                side_effect=RuntimeError("runtime"),
            ),
            patch("backend.src.rag.rag_pipeline.get_generator"),
            patch("backend.src.rag.rag_pipeline.get_uncertainty_estimator"),
        ):
            result = process_query("query")

        assert "error" in result
        assert "runtime" in result["error"]
