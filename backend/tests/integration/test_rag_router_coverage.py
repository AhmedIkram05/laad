"""High-value coverage for backend/src/rag/router.py.

Uses a standalone FastAPI app with an overridden auth dependency so no DB
login is needed. All retriever/generator/DB/redis/agent boundaries mocked.
"""

import asyncio
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from backend.src.auth.auth_router import get_current_user
from backend.src.rag import router as rag_router
from backend.src.rag.retriever import RetrievedChunk
from backend.src.rag.utils import QueryType

pytestmark = pytest.mark.rag


def _make_client(user=None):
    app = FastAPI()
    app.include_router(rag_router.router)
    app.dependency_overrides[get_current_user] = lambda: user or {"sub": "testuser"}
    return TestClient(app, raise_server_exceptions=False)


def _chunk(**over):
    base = {
        "text": "Network timeout at ATM-GB-0001",
        "chunk_id": "doc_1",
        "atm_id": "ATM-GB-0001",
        "timestamp": "2026-05-15T10:00:00Z",
        "distance": 0.1,
        "confidence_score": 0.9,
    }
    base.update(over)
    return RetrievedChunk(**base)


def _generated(text="The error means timeout.", **over):
    from backend.src.rag.generator import GeneratedResponse

    kwargs = {
        "text": text,
        "sources": [_chunk()],
        "model": "test-model",
        "raw_response": {},
    }
    kwargs.update(over)
    return GeneratedResponse(**kwargs)


def _uncertainty(conf=0.85, **over):
    from backend.src.rag.uncertainty import UncertaintyEstimate

    kwargs = {
        "final_confidence": conf,
        "confidence_level": "high",
        "self_consistency_score": 0.85,
        "verbalized_confidence": None,
        "generation_variance": None,
        "grounding_score": None,
        "is_uncertain": False,
        "recommendation": "Auto-respond",
    }
    kwargs.update(over)
    return UncertaintyEstimate(**kwargs)


def _agent_result(**over):
    result = {
        "answer": "Agent answer.",
        "sources": [
            {
                "text": "Network timeout at ATM-GB-0001",
                "chunk_id": "row:1",
                "atm_id": "ATM-GB-0001",
                "timestamp": "2026-05-15T10:00:00Z",
                "confidence_score": 0.9,
            }
        ],
        "uncertainty_score": 0.85,
        "confidence_level": "high",
        "is_uncertain": False,
        "recommendation": "Auto-respond",
        "model_used": "agentic",
        "self_consistency_score": 0.9,
        "verbalized_confidence": 0.8,
        "grounding_score": 0.9,
        "generation_variance": 0.1,
        "cross_encoder_used": False,
        "was_revised": False,
        "critique_text": None,
        "agent_trace": {"mode": "agentic", "rounds": 1},
    }
    result.update(over)
    return result


@pytest.fixture(autouse=True)
def _clean_rate_limit():
    rag_router._query_timestamps.clear()
    yield
    rag_router._query_timestamps.clear()


@pytest.fixture(autouse=True)
def _no_redis():
    with patch.object(rag_router, "get_redis_client", return_value=None):
        yield


class TestRateLimit:
    def test_in_memory_allows_then_blocks(self):
        for _ in range(rag_router.RATE_LIMIT_MAX_REQUESTS):
            rag_router._check_rate_limit_in_memory("u1")
        with pytest.raises(HTTPException) as exc:
            rag_router._check_rate_limit_in_memory("u1")
        assert exc.value.status_code == 429

    def test_in_memory_window_expiry(self):
        import time

        rag_router._query_timestamps["u2"] = [time.time() - 10_000.0]
        rag_router._check_rate_limit_in_memory("u2")
        assert len(rag_router._query_timestamps["u2"]) == 1

    def test_redis_none_falls_back(self):
        rag_router._check_rate_limit("anon")
        assert len(rag_router._query_timestamps["anon"]) == 1

    def test_redis_allows_under_limit(self):
        pipe = MagicMock()
        pipe.execute.return_value = [None, None, 5, None]
        client = MagicMock()
        client.pipeline.return_value = pipe
        with patch.object(rag_router, "get_redis_client", return_value=client):
            rag_router._check_rate_limit("u3")

    def test_redis_blocks_over_limit(self):
        pipe = MagicMock()
        pipe.execute.return_value = [None, None, 99, None]
        client = MagicMock()
        client.pipeline.return_value = pipe
        with patch.object(rag_router, "get_redis_client", return_value=client):
            with pytest.raises(HTTPException) as exc:
                rag_router._check_rate_limit("u4")
            assert exc.value.status_code == 429


class TestChampionQuery:
    def _run(self, **kw):
        defaults = {
            "query": "q",
            "sanitized_query": "q",
            "atm_id": None,
            "top_k": 5,
            "current_user": {"sub": "testuser"},
        }
        defaults.update(kw)
        return asyncio.run(rag_router._run_champion_query(**defaults))

    def test_exception_fallback_disabled_raises_500(self):
        with (
            patch(
                "backend.src.rag.agent.run_agent_query", side_effect=RuntimeError("x")
            ),
            patch.object(rag_router.config, "champion_fallback", False),
        ):
            with pytest.raises(HTTPException) as exc:
                self._run()
            assert exc.value.status_code == 500

    def test_exception_fallback_enabled_returns_none(self):
        with (
            patch(
                "backend.src.rag.agent.run_agent_query", side_effect=RuntimeError("x")
            ),
            patch.object(rag_router.config, "champion_fallback", True),
        ):
            assert self._run() is None

    def test_error_no_sources_fallback_disabled_raises_404(self):
        with (
            patch(
                "backend.src.rag.agent.run_agent_query",
                return_value={"error": "bad", "sources": []},
            ),
            patch.object(rag_router.config, "champion_fallback", False),
        ):
            with pytest.raises(HTTPException) as exc:
                self._run()
            assert exc.value.status_code == 404

    def test_error_with_sources_fallback_disabled_raises_500(self):
        with (
            patch(
                "backend.src.rag.agent.run_agent_query",
                return_value={"error": "bad", "sources": [{"text": "t"}]},
            ),
            patch.object(rag_router.config, "champion_fallback", False),
        ):
            with pytest.raises(HTTPException) as exc:
                self._run()
            assert exc.value.status_code == 500

    def test_miss_fallback_enabled_returns_none(self):
        with (
            patch(
                "backend.src.rag.agent.run_agent_query",
                return_value={"sources": []},
            ),
            patch.object(rag_router.config, "champion_fallback", True),
        ):
            assert self._run() is None

    def test_success_saves_history_and_caches(self):
        with (
            patch(
                "backend.src.rag.agent.run_agent_query",
                return_value=_agent_result(),
            ),
            patch.object(rag_router, "_get_user_id_from_username", return_value=7),
            patch.object(rag_router, "_save_query_history", return_value=42) as hist,
            patch.object(rag_router, "_save_agent_trace") as trace,
            patch.object(rag_router, "set_cached_response") as cache,
        ):
            resp = self._run()
            assert resp.query_id == 42
            assert resp.answer == "Agent answer."
            assert resp.model_used == "agentic"
            hist.assert_called_once()
            trace.assert_called_once_with(42, {"mode": "agentic", "rounds": 1})
            cache.assert_called_once()

    def test_success_falls_back_to_anonymous_history(self):
        with (
            patch(
                "backend.src.rag.agent.run_agent_query",
                return_value=_agent_result(),
            ),
            patch.object(rag_router, "_get_user_id_from_username", return_value=None),
            patch.object(rag_router, "_save_query_history", return_value=None),
            patch.object(rag_router, "_save_query_history_fallback", return_value=99),
            patch.object(rag_router, "_save_agent_trace"),
            patch.object(rag_router, "set_cached_response"),
        ):
            resp = self._run()
            assert resp.query_id == 99


class TestLegacyQuery:
    def _run(self, **kw):
        defaults = {
            "query": "q",
            "sanitized_query": "q",
            "query_type": QueryType.GENERAL,
            "atm_id": None,
            "anomaly_type": None,
            "error_only": False,
            "most_recent_first": False,
            "top_k": 5,
            "include_uncertainty": True,
            "enable_reflexion": False,
            "enable_citation_grounding": False,
            "enable_self_consistency": False,
            "current_user": {"sub": "testuser"},
        }
        defaults.update(kw)
        return rag_router._run_legacy_query(**defaults)

    def test_no_chunks_raises_404(self):
        with (
            patch.object(rag_router, "get_retriever") as gr,
            patch.object(rag_router, "get_generator"),
            patch.object(rag_router, "get_uncertainty_estimator"),
        ):
            gr.return_value.retrieve.return_value = []
            with pytest.raises(HTTPException) as exc:
                self._run()
            assert exc.value.status_code == 404

    def test_success_with_uncertainty(self):
        with (
            patch.object(rag_router, "get_retriever") as gr,
            patch.object(rag_router, "get_generator") as gg,
            patch.object(rag_router, "get_uncertainty_estimator") as gu,
            patch.object(rag_router, "_get_user_id_from_username", return_value=3),
            patch.object(rag_router, "_save_query_history", return_value=11),
            patch.object(rag_router, "set_cached_response"),
        ):
            gr.return_value.retrieve.return_value = [_chunk()]
            gg.return_value.generate.return_value = _generated()
            gu.return_value.estimate.return_value = _uncertainty()
            resp = self._run()
            assert resp.query_id == 11
            assert resp.confidence_level == "high"
            assert resp.model_used == "test-model"

    def test_success_without_uncertainty_uses_defaults(self):
        with (
            patch.object(rag_router, "get_retriever") as gr,
            patch.object(rag_router, "get_generator") as gg,
            patch.object(rag_router, "get_uncertainty_estimator"),
            patch.object(rag_router, "_get_user_id_from_username", return_value=None),
            patch.object(rag_router, "_save_query_history", return_value=None),
            patch.object(rag_router, "_save_query_history_fallback", return_value=5),
            patch.object(rag_router, "set_cached_response"),
        ):
            gen = _generated(critique_text="fix this")
            gr.return_value.retrieve.return_value = [_chunk()]
            gg.return_value.generate.return_value = gen
            resp = self._run(include_uncertainty=False)
            assert resp.query_id == 5
            assert resp.uncertainty_score == 0.5
            assert resp.confidence_level == "medium"
            assert resp.critique_text == "fix this"


class TestQueryEndpoint:
    def test_validation_error_empty_query(self):
        client = _make_client()
        resp = client.post("/api/rag/query", json={"query": ""})
        assert resp.status_code == 422

    def test_cache_hit_short_circuits(self):
        client = _make_client()
        top_k = rag_router.config.retrieval_top_k
        cached = {
            "query_id": 1,
            "answer": "cached answer",
            "sources": [
                {
                    "text": "t",
                    "chunk_id": "c",
                    "atm_id": "ATM-1",
                    "timestamp": "2026-01-01",
                    "confidence_score": 0.9,
                }
            ],
            "uncertainty_score": 0.9,
            "confidence_level": "high",
            "is_uncertain": False,
            "recommendation": "ok",
        }
        with (
            patch.object(rag_router, "get_cached_response", return_value=cached),
            patch("backend.src.rag.agent.run_agent_query") as agent,
        ):
            resp = client.post(
                "/api/rag/query", json={"query": "plain question", "top_k": top_k}
            )
            assert resp.status_code == 200
            assert resp.json()["model_used"] == "cache"
            agent.assert_not_called()

    def test_champion_hit_returns_agent_answer(self):
        client = _make_client()
        with (
            patch.object(rag_router, "get_cached_response", return_value=None),
            patch(
                "backend.src.rag.agent.run_agent_query",
                return_value=_agent_result(),
            ),
            patch.object(rag_router, "_get_user_id_from_username", return_value=1),
            patch.object(rag_router, "_save_query_history", return_value=2),
            patch.object(rag_router, "_save_agent_trace"),
            patch.object(rag_router, "set_cached_response"),
        ):
            resp = client.post("/api/rag/query", json={"query": "plain question"})
            assert resp.status_code == 200
            assert resp.json()["model_used"] == "agentic"

    def test_champion_miss_falls_back_to_legacy(self):
        client = _make_client()
        with (
            patch.object(rag_router, "get_cached_response", return_value=None),
            patch(
                "backend.src.rag.agent.run_agent_query",
                return_value={"sources": []},
            ),
            patch.object(rag_router, "get_retriever") as gr,
            patch.object(rag_router, "get_generator") as gg,
            patch.object(rag_router, "get_uncertainty_estimator") as gu,
            patch.object(rag_router, "_get_user_id_from_username", return_value=1),
            patch.object(rag_router, "_save_query_history", return_value=3),
            patch.object(rag_router, "set_cached_response"),
        ):
            gr.return_value.retrieve.return_value = [_chunk()]
            gg.return_value.generate.return_value = _generated()
            gu.return_value.estimate.return_value = _uncertainty()
            resp = client.post("/api/rag/query", json={"query": "plain question"})
            assert resp.status_code == 200
            assert resp.json()["query_id"] == 3

    def test_legacy_404_propagates(self):
        client = _make_client()
        with (
            patch.object(rag_router, "get_cached_response", return_value=None),
            patch.object(rag_router.config, "champion", "legacy"),
            patch.object(rag_router, "get_retriever") as gr,
            patch.object(rag_router, "get_generator"),
            patch.object(rag_router, "get_uncertainty_estimator"),
        ):
            gr.return_value.retrieve.return_value = []
            resp = client.post("/api/rag/query", json={"query": "plain question"})
            assert resp.status_code == 404

    def test_internal_error_maps_to_500(self):
        client = _make_client()
        top_k = rag_router.config.retrieval_top_k
        with patch.object(
            rag_router, "get_cached_response", side_effect=RuntimeError("boom")
        ):
            resp = client.post(
                "/api/rag/query", json={"query": "plain question", "top_k": top_k}
            )
            assert resp.status_code == 500

    def test_rate_limited_returns_429(self):
        client = _make_client()
        with patch.object(
            rag_router,
            "_check_rate_limit",
            side_effect=rag_router.HTTPException(status_code=429, detail="slow"),
        ):
            resp = client.post("/api/rag/query", json={"query": "plain question"})
            assert resp.status_code == 429

    def test_stats_query_hits_db_path(self):
        client = _make_client()
        cur = MagicMock()
        cur.fetchone.side_effect = [
            {"total": 4},
            {"active": 3},
            {"resolved": 1},
        ]
        cur.fetchall.side_effect = [
            [{"anomaly_type": "A1", "count": 4}],
            [{"atm_id": "ATM-1", "count": 4}],
            [{"severity": "CRITICAL", "count": 4}],
        ]
        ctx = MagicMock()
        ctx.__enter__.return_value = cur
        ctx.__exit__.return_value = False
        with patch.object(rag_router, "get_cursor", return_value=ctx):
            resp = client.post(
                "/api/rag/query", json={"query": "how many anomalies total"}
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["model_used"] == "db_stats"
            assert "Total anomalies: 4" in body["answer"]

    def test_stats_query_db_failure_maps_to_500(self):
        client = _make_client()
        with patch.object(
            rag_router, "get_cursor", side_effect=RuntimeError("db down")
        ):
            resp = client.post(
                "/api/rag/query", json={"query": "how many anomalies total"}
            )
            assert resp.status_code == 500

    def test_explicit_filters_skip_cache(self):
        client = _make_client()
        with (
            patch.object(rag_router, "get_cached_response") as gc,
            patch.object(rag_router.config, "champion", "legacy"),
            patch.object(rag_router, "get_retriever") as gr,
            patch.object(rag_router, "get_generator") as gg,
            patch.object(rag_router, "get_uncertainty_estimator") as gu,
            patch.object(rag_router, "_get_user_id_from_username", return_value=1),
            patch.object(rag_router, "_save_query_history", return_value=8),
            patch.object(rag_router, "set_cached_response"),
        ):
            gr.return_value.retrieve.return_value = [_chunk()]
            gg.return_value.generate.return_value = _generated()
            gu.return_value.estimate.return_value = _uncertainty()
            resp = client.post(
                "/api/rag/query",
                json={"query": "plain question", "atm_id": "ATM-1", "top_k": 3},
            )
            assert resp.status_code == 200
            gc.assert_not_called()


class TestAgentEndpoint:
    def test_cache_hit_returns_cached(self):
        client = _make_client()
        cached = _agent_result()
        with (
            patch.object(rag_router, "get_cached_response", return_value=cached),
            patch("backend.src.rag.agent.run_agent_query") as agent,
        ):
            resp = client.post(
                "/api/rag/agent",
                json={"query": "troubleshoot ATM-1", "mode": "hybrid"},
            )
            assert resp.status_code == 200
            agent.assert_not_called()

    def test_error_result_maps_to_500(self):
        client = _make_client()
        with (
            patch.object(rag_router, "get_cached_response", return_value=None),
            patch(
                "backend.src.rag.agent.run_agent_query",
                return_value={"error": "boom", "sources": []},
            ),
        ):
            resp = client.post("/api/rag/agent", json={"query": "boom query"})
            assert resp.status_code == 500

    def test_no_sources_maps_to_404(self):
        client = _make_client()
        with (
            patch.object(rag_router, "get_cached_response", return_value=None),
            patch(
                "backend.src.rag.agent.run_agent_query",
                return_value={"answer": "x", "sources": []},
            ),
        ):
            resp = client.post("/api/rag/agent", json={"query": "empty query"})
            assert resp.status_code == 404

    def test_success_strips_trace_when_not_requested(self):
        client = _make_client()
        with (
            patch.object(rag_router, "get_cached_response", return_value=None),
            patch(
                "backend.src.rag.agent.run_agent_query",
                return_value=_agent_result(),
            ),
            patch.object(rag_router, "_get_user_id_from_username", return_value=1),
            patch.object(rag_router, "_save_query_history", return_value=None),
            patch.object(rag_router, "_save_query_history_fallback", return_value=6),
            patch.object(rag_router, "_save_agent_trace"),
            patch.object(rag_router, "set_cached_response"),
        ):
            resp = client.post(
                "/api/rag/agent",
                json={"query": "fix it", "include_trace": False},
            )
            assert resp.status_code == 200
            assert resp.json()["agent_trace"] is None

    def test_invalid_mode_maps_to_500(self):
        client = _make_client()
        with patch.object(rag_router, "get_cached_response", return_value=None):
            resp = client.post(
                "/api/rag/agent", json={"query": "fix it", "mode": "nope"}
            )
            assert resp.status_code == 422

    def test_unexpected_exception_maps_to_500(self):
        client = _make_client()
        with patch.object(
            rag_router, "get_cached_response", side_effect=RuntimeError("boom")
        ):
            resp = client.post("/api/rag/agent", json={"query": "fix it"})
            assert resp.status_code == 500


class TestFeedbackHistoryStats:
    def test_feedback_success(self):
        client = _make_client()
        with (
            patch.object(rag_router, "_get_user_id_from_username", return_value=1),
            patch.object(rag_router, "_get_query_by_id", return_value={"id": 1}),
        ):
            resp = client.post(
                "/api/rag/feedback", json={"query_id": 1, "feedback": "helpful"}
            )
            assert resp.status_code == 200
            assert resp.json()["success"] is True

    def test_feedback_missing_query_returns_404(self):
        client = _make_client()
        with (
            patch.object(rag_router, "_get_user_id_from_username", return_value=1),
            patch.object(rag_router, "_get_query_by_id", return_value=None),
        ):
            resp = client.post(
                "/api/rag/feedback", json={"query_id": 999, "feedback": "helpful"}
            )
            assert resp.status_code == 404

    def test_feedback_exception_maps_to_500(self):
        client = _make_client()
        with patch.object(
            rag_router, "_get_user_id_from_username", side_effect=RuntimeError("x")
        ):
            resp = client.post(
                "/api/rag/feedback", json={"query_id": 1, "feedback": "helpful"}
            )
            assert resp.status_code == 500

    def test_history_success(self):
        client = _make_client()
        cur = MagicMock()
        cur.fetchall.return_value = [
            {
                "id": 1,
                "query_text": "q",
                "answer_text": "a",
                "uncertainty_score": 0.5,
                "created_at": datetime(2026, 1, 1, 12, 0, 0),
            },
            {
                "id": 2,
                "query_text": "q2",
                "answer_text": "a2",
                "uncertainty_score": 0.7,
                "created_at": None,
            },
        ]
        cur.fetchone.return_value = {"total": 2}
        ctx = MagicMock()
        ctx.__enter__.return_value = cur
        ctx.__exit__.return_value = False
        with (
            patch.object(rag_router, "_get_user_id_from_username", return_value=1),
            patch.object(rag_router, "get_cursor", return_value=ctx),
        ):
            resp = client.get("/api/rag/history?limit=10&offset=0")
            assert resp.status_code == 200
            body = resp.json()
            assert body["total"] == 2
            assert body["history"][0]["created_at"].startswith("2026-01-01")
            assert body["history"][1]["created_at"] == ""

    def test_history_failure_maps_to_500(self):
        client = _make_client()
        with (
            patch.object(rag_router, "_get_user_id_from_username", return_value=1),
            patch.object(rag_router, "get_cursor", side_effect=RuntimeError("db down")),
        ):
            assert client.get("/api/rag/history").status_code == 500

    def test_stats_success(self):
        client = _make_client()
        cur = MagicMock()
        cur.fetchone.return_value = {"total": 12}
        ctx = MagicMock()
        ctx.__enter__.return_value = cur
        ctx.__exit__.return_value = False
        retriever = MagicMock()
        retriever.get_collection_stats.return_value = {"total_chunks": 77}
        with (
            patch.object(rag_router, "get_retriever", return_value=retriever),
            patch.object(rag_router, "get_cursor", return_value=ctx),
        ):
            resp = client.get("/api/rag/stats")
            body = resp.json()
            assert resp.status_code == 200
            assert body["collection_chunks"] == 77
            assert body["total_queries"] == 12

    def test_stats_failure_maps_to_500(self):
        client = _make_client()
        with patch.object(
            rag_router, "get_retriever", side_effect=RuntimeError("chroma down")
        ):
            assert client.get("/api/rag/stats").status_code == 500

    def test_anomaly_stats_with_filters(self):
        client = _make_client()
        cur = MagicMock()
        cur.fetchone.side_effect = [
            {"total": 10},
            {"active": 6},
            {"resolved": 4},
        ]
        cur.fetchall.side_effect = [
            [{"anomaly_type": "A1", "count": 10}],
            [{"atm_id": "ATM-1", "count": 10}],
            [{"severity": "CRITICAL", "count": 10}],
        ]
        ctx = MagicMock()
        ctx.__enter__.return_value = cur
        ctx.__exit__.return_value = False
        with patch.object(rag_router, "get_cursor", return_value=ctx):
            resp = client.get("/api/rag/anomalies/stats?atm_id=ATM-1&anomaly_type=A1")
            assert resp.status_code == 200
            body = resp.json()
            assert body["total"] == 10
            assert body["by_type"] == {"A1": 10}
            assert body["active"] == 6

    def test_anomaly_stats_failure_maps_to_500(self):
        client = _make_client()
        with patch.object(
            rag_router, "get_cursor", side_effect=RuntimeError("db down")
        ):
            assert client.get("/api/rag/anomalies/stats").status_code == 500


class TestDbHelpers:
    def test_save_agent_trace_delegates(self):
        with patch.object(rag_router, "record_trace") as rec:
            rag_router._save_agent_trace(5, {"mode": "x"})
            rec.assert_called_once_with(5, {"mode": "x"})

    def test_get_user_id_empty_returns_none(self):
        assert rag_router._get_user_id_from_username("") is None

    def test_get_user_id_found_and_missing(self):
        cur = MagicMock()
        cur.fetchone.side_effect = [{"id": 9}, None]
        ctx = MagicMock()
        ctx.__enter__.return_value = cur
        ctx.__exit__.return_value = False
        with patch.object(rag_router, "get_cursor", return_value=ctx):
            assert rag_router._get_user_id_from_username("ann") == 9
            assert rag_router._get_user_id_from_username("ghost") is None

    def test_get_user_id_exception_returns_none(self):
        with patch.object(
            rag_router, "get_cursor", side_effect=RuntimeError("db down")
        ):
            assert rag_router._get_user_id_from_username("ann") is None

    def test_save_history_none_user_returns_none(self):
        assert (
            rag_router._save_query_history(
                user_id=None, query="q", answer="a", uncertainty_score=0.5
            )
            is None
        )

    def test_save_history_success_and_failure(self):
        cur = MagicMock()
        cur.fetchone.return_value = {"id": 21}
        ctx = MagicMock()
        ctx.__enter__.return_value = cur
        ctx.__exit__.return_value = False
        with patch.object(rag_router, "get_cursor", return_value=ctx):
            assert (
                rag_router._save_query_history(
                    user_id=1, query="q", answer="a", uncertainty_score=0.5
                )
                == 21
            )
        with patch.object(
            rag_router, "get_cursor", side_effect=RuntimeError("db down")
        ):
            assert (
                rag_router._save_query_history(
                    user_id=1, query="q", answer="a", uncertainty_score=0.5
                )
                is None
            )

    def test_save_history_none_row_returns_none(self):
        cur = MagicMock()
        cur.fetchone.return_value = None
        ctx = MagicMock()
        ctx.__enter__.return_value = cur
        ctx.__exit__.return_value = False
        with patch.object(rag_router, "get_cursor", return_value=ctx):
            assert (
                rag_router._save_query_history(
                    user_id=1, query="q", answer="a", uncertainty_score=0.5
                )
                is None
            )

    def test_fallback_history_no_admin_returns_none(self):
        cur = MagicMock()
        cur.fetchone.return_value = None
        ctx = MagicMock()
        ctx.__enter__.return_value = cur
        ctx.__exit__.return_value = False
        with patch.object(rag_router, "get_cursor", return_value=ctx):
            assert (
                rag_router._save_query_history_fallback(
                    query="q", answer="a", uncertainty_score=0.5
                )
                is None
            )

    def test_fallback_history_success(self):
        admin_cur = MagicMock()
        admin_cur.fetchone.return_value = {"id": 1}
        admin_ctx = MagicMock()
        admin_ctx.__enter__.return_value = admin_cur
        admin_ctx.__exit__.return_value = False
        ins_cur = MagicMock()
        ins_cur.fetchone.return_value = {"id": 33}
        ins_ctx = MagicMock()
        ins_ctx.__enter__.return_value = ins_cur
        ins_ctx.__exit__.return_value = False
        with patch.object(rag_router, "get_cursor", side_effect=[admin_ctx, ins_ctx]):
            assert (
                rag_router._save_query_history_fallback(
                    query="q", answer="a", uncertainty_score=0.5
                )
                == 33
            )

    def test_fallback_history_exception_returns_none(self):
        with patch.object(
            rag_router, "get_cursor", side_effect=RuntimeError("db down")
        ):
            assert (
                rag_router._save_query_history_fallback(
                    query="q", answer="a", uncertainty_score=0.5
                )
                is None
            )

    def test_get_query_by_id_variants(self):
        assert rag_router._get_query_by_id(None, 1) is None

        cur = MagicMock()
        cur.fetchone.return_value = {"id": 1, "query_text": "q"}
        ctx = MagicMock()
        ctx.__enter__.return_value = cur
        ctx.__exit__.return_value = False
        with patch.object(rag_router, "get_cursor", return_value=ctx):
            assert rag_router._get_query_by_id(1, 2) == {"id": 1, "query_text": "q"}
            assert rag_router._get_query_by_id(1, None) == {
                "id": 1,
                "query_text": "q",
            }

        cur2 = MagicMock()
        cur2.fetchone.return_value = None
        ctx2 = MagicMock()
        ctx2.__enter__.return_value = cur2
        ctx2.__exit__.return_value = False
        with patch.object(rag_router, "get_cursor", return_value=ctx2):
            assert rag_router._get_query_by_id(999, 1) is None

        with patch.object(
            rag_router, "get_cursor", side_effect=RuntimeError("db down")
        ):
            assert rag_router._get_query_by_id(1, 1) is None

    def test_handle_stats_query_empty_groups(self):
        cur = MagicMock()
        cur.fetchone.side_effect = [
            {"total": 0},
            {"active": 0},
            {"resolved": 0},
        ]
        cur.fetchall.side_effect = [[], [], []]
        ctx = MagicMock()
        ctx.__enter__.return_value = cur
        ctx.__exit__.return_value = False
        with patch.object(rag_router, "get_cursor", return_value=ctx):
            resp = asyncio.run(
                rag_router._handle_stats_query(
                    query="how many",
                    atm_id=None,
                    anomaly_type=None,
                    current_user={"sub": "u"},
                )
            )
            assert "Total anomalies: 0" in resp.answer
            assert resp.model_used == "db_stats"

    def test_handle_stats_query_with_filters(self):
        cur = MagicMock()
        cur.fetchone.side_effect = [
            {"total": 2},
            {"active": 2},
            {"resolved": 0},
        ]
        cur.fetchall.side_effect = [
            [{"anomaly_type": "A1", "count": 2}],
            [{"atm_id": "ATM-1", "count": 2}],
            [{"severity": "CRITICAL", "count": 2}],
        ]
        ctx = MagicMock()
        ctx.__enter__.return_value = cur
        ctx.__exit__.return_value = False
        with patch.object(rag_router, "get_cursor", return_value=ctx):
            resp = asyncio.run(
                rag_router._handle_stats_query(
                    query="how many",
                    atm_id="ATM-1",
                    anomaly_type="A1",
                    current_user={"sub": "u"},
                )
            )
            assert "Total anomalies: 2" in resp.answer
            assert "A1: 2" in resp.answer
            assert "ATM-1: 2" in resp.answer
            assert "CRITICAL: 2" in resp.answer
            assert "AND atm_id = %s" in cur.execute.call_args_list[0][0][0]
