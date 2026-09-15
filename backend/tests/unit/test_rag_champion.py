"""Tests for agentic champion routing in POST /api/rag/query."""

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

pytestmark = pytest.mark.rag


def _agent_result(sources=None, **overrides):
    result = {
        "answer": "agent answer",
        "sources": [
            {
                "text": "Network timeout at ATM-GB-0001",
                "chunk_id": "doc_1",
                "atm_id": "ATM-GB-0001",
                "timestamp": "2026-05-15T10:00:00Z",
                "confidence_score": 0.9,
            }
        ],
        "uncertainty_score": 0.9,
        "confidence_level": "high",
        "is_uncertain": False,
        "recommendation": "Auto-respond",
        "model_used": "agentic-model",
    }
    if sources is not None:
        result["sources"] = sources
    result.update(overrides)
    return result


def _setup_legacy(mock_ret, mock_gen, mock_unc, answer="legacy answer"):
    from backend.src.rag.generator import GeneratedResponse
    from backend.src.rag.retriever import RetrievedChunk
    from backend.src.rag.uncertainty import UncertaintyEstimate

    chunk = RetrievedChunk(
        text="Network timeout at ATM-GB-0001",
        chunk_id="doc_1",
        atm_id="ATM-GB-0001",
        timestamp="2026-05-15T10:00:00Z",
        distance=0.1,
        confidence_score=0.9,
    )
    mock_ret.return_value.retrieve.return_value = [chunk]
    mock_gen.return_value.generate.return_value = GeneratedResponse(
        text=answer, sources=[chunk], model="legacy-model", raw_response={}
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


def _call_query(query="Explain logs"):
    from backend.src.rag import router
    from backend.src.rag.schemas import RAGQueryRequest

    router._query_timestamps.clear()
    return asyncio.run(
        router.query(
            request=RAGQueryRequest(query=query),
            req=MagicMock(),
            current_user={"sub": "admin"},
        )
    )


class TestChampionConfig:
    def test_defaults(self):
        with patch.dict(os.environ, {}, clear=True):
            from importlib import reload
            import backend.src.rag.config as cfg

            reload(cfg)
            c = cfg.RAGConfig()
            assert c.champion == "agentic"
            assert c.champion_fallback is True

    def test_env_override(self):
        with patch.dict(
            os.environ,
            {"RAG_CHAMPION": "legacy", "RAG_CHAMPION_FALLBACK": "false"},
            clear=True,
        ):
            from importlib import reload
            import backend.src.rag.config as cfg

            reload(cfg)
            c = cfg.RAGConfig()
            assert c.champion == "legacy"
            assert c.champion_fallback is False

    def test_invalid_numeric_falls_back_to_defaults(self):
        with patch.dict(os.environ, {"RAG_TOP_K": "bad"}, clear=True):
            from importlib import reload
            import backend.src.rag.config as cfg

            reload(cfg)
            c = cfg.RAGConfig()
            assert c.champion == "agentic"
            assert c.champion_fallback is True


class TestChampionQuery:
    def test_champion_success(self):
        from backend.src.rag import router

        payload = _agent_result()
        with (
            patch.object(router, "_check_rate_limit", lambda *a, **k: None),
            patch("backend.src.rag.router.get_cached_response", return_value=None),
            patch("backend.src.rag.router.set_cached_response"),
            patch("backend.src.rag.router._get_user_id_from_username", return_value=1),
            patch(
                "backend.src.rag.router._save_query_history", return_value=7
            ) as mock_hist,
            patch("backend.src.rag.router._save_agent_trace"),
            patch.object(router.config, "champion", "agentic"),
            patch.object(router.config, "champion_fallback", True),
            patch(
                "backend.src.rag.agent.run_agent_query",
                new=AsyncMock(return_value=payload),
            ) as mock_run,
        ):
            resp = _call_query()
        assert resp.answer == "agent answer"
        assert len(resp.sources) == 1
        assert resp.model_used == "agentic-model"
        assert resp.query_id == 7
        mock_hist.assert_called_once()
        mock_run.assert_awaited_once()

    def test_champion_empty_sources_falls_back_to_legacy(self):
        from backend.src.rag import router

        with (
            patch.object(router, "_check_rate_limit", lambda *a, **k: None),
            patch("backend.src.rag.router.get_cached_response", return_value=None),
            patch("backend.src.rag.router.set_cached_response"),
            patch("backend.src.rag.router._get_user_id_from_username", return_value=1),
            patch("backend.src.rag.router._save_query_history", return_value=7),
            patch("backend.src.rag.router._save_agent_trace"),
            patch("backend.src.rag.router.get_retriever") as mock_ret,
            patch("backend.src.rag.router.get_generator") as mock_gen,
            patch("backend.src.rag.router.get_uncertainty_estimator") as mock_unc,
            patch.object(router.config, "champion", "agentic"),
            patch.object(router.config, "champion_fallback", True),
            patch(
                "backend.src.rag.agent.run_agent_query",
                new=AsyncMock(return_value=_agent_result(sources=[])),
            ),
        ):
            _setup_legacy(mock_ret, mock_gen, mock_unc)
            resp = _call_query()
        assert resp.answer == "legacy answer"
        assert resp.model_used == "legacy-model"

    def test_champion_empty_sources_no_fallback_404(self):
        from backend.src.rag import router

        with (
            patch.object(router, "_check_rate_limit", lambda *a, **k: None),
            patch("backend.src.rag.router.get_cached_response", return_value=None),
            patch("backend.src.rag.router.set_cached_response"),
            patch.object(router.config, "champion", "agentic"),
            patch.object(router.config, "champion_fallback", False),
            patch(
                "backend.src.rag.agent.run_agent_query",
                new=AsyncMock(return_value=_agent_result(sources=[])),
            ),
            pytest.raises(HTTPException) as exc,
        ):
            _call_query()
        assert exc.value.status_code == 404

    def test_champion_error_no_fallback_500(self):
        from backend.src.rag import router

        payload = _agent_result(error="boom")
        with (
            patch.object(router, "_check_rate_limit", lambda *a, **k: None),
            patch("backend.src.rag.router.get_cached_response", return_value=None),
            patch("backend.src.rag.router.set_cached_response"),
            patch.object(router.config, "champion", "agentic"),
            patch.object(router.config, "champion_fallback", False),
            patch(
                "backend.src.rag.agent.run_agent_query",
                new=AsyncMock(return_value=payload),
            ),
        ):
            with pytest.raises(HTTPException) as exc:
                _call_query()
        assert exc.value.status_code == 500

    def test_champion_exception_falls_back_to_legacy(self):
        from backend.src.rag import router

        with (
            patch.object(router, "_check_rate_limit", lambda *a, **k: None),
            patch("backend.src.rag.router.get_cached_response", return_value=None),
            patch("backend.src.rag.router.set_cached_response"),
            patch("backend.src.rag.router._get_user_id_from_username", return_value=1),
            patch("backend.src.rag.router._save_query_history", return_value=7),
            patch("backend.src.rag.router._save_agent_trace"),
            patch("backend.src.rag.router.get_retriever") as mock_ret,
            patch("backend.src.rag.router.get_generator") as mock_gen,
            patch("backend.src.rag.router.get_uncertainty_estimator") as mock_unc,
            patch.object(router.config, "champion", "agentic"),
            patch.object(router.config, "champion_fallback", True),
            patch(
                "backend.src.rag.agent.run_agent_query",
                new=AsyncMock(side_effect=RuntimeError("boom")),
            ),
        ):
            _setup_legacy(mock_ret, mock_gen, mock_unc)
            resp = _call_query()
        assert resp.answer == "legacy answer"

    def test_legacy_mode_skips_agent(self):
        from backend.src.rag import router

        with (
            patch.object(router, "_check_rate_limit", lambda *a, **k: None),
            patch("backend.src.rag.router.get_cached_response", return_value=None),
            patch("backend.src.rag.router.set_cached_response"),
            patch("backend.src.rag.router._get_user_id_from_username", return_value=1),
            patch("backend.src.rag.router._save_query_history", return_value=7),
            patch("backend.src.rag.router._save_agent_trace"),
            patch("backend.src.rag.router.get_retriever") as mock_ret,
            patch("backend.src.rag.router.get_generator") as mock_gen,
            patch("backend.src.rag.router.get_uncertainty_estimator") as mock_unc,
            patch.object(router.config, "champion", "legacy"),
            patch(
                "backend.src.rag.agent.run_agent_query",
                new=AsyncMock(return_value=_agent_result()),
            ) as mock_run,
        ):
            _setup_legacy(mock_ret, mock_gen, mock_unc)
            resp = _call_query()
        mock_run.assert_not_called()
        assert resp.answer == "legacy answer"

    def test_cache_hit_short_circuits_champion(self):
        from backend.src.rag import router

        cached = {
            "query_id": 99,
            "answer": "cached answer",
            "sources": [
                {
                    "text": "cached log",
                    "chunk_id": "doc_9",
                    "atm_id": "ATM-GB-0001",
                    "timestamp": "2026-05-15T10:00:00Z",
                    "confidence_score": 0.9,
                }
            ],
            "uncertainty_score": 0.8,
            "confidence_level": "high",
            "is_uncertain": False,
            "recommendation": "Auto-respond",
        }
        with (
            patch.object(router, "_check_rate_limit", lambda *a, **k: None),
            patch("backend.src.rag.router.get_cached_response", return_value=cached),
            patch.object(router.config, "champion", "agentic"),
            # Cache is only consulted for default retrieval settings; the
            # schema default top_k=10 must match config.retrieval_top_k for
            # use_cache to evaluate True in any environment (test env sets
            # RAG_TOP_K=3).
            patch.object(router.config, "retrieval_top_k", 10),
            patch(
                "backend.src.rag.agent.run_agent_query",
                new=AsyncMock(return_value=_agent_result()),
            ) as mock_run,
        ):
            resp = _call_query()
        mock_run.assert_not_called()
        assert resp.model_used == "cache"
        assert resp.answer == "cached answer"
