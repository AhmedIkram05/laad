"""Regression tests: blocking RAG I/O must not run on the event loop.

Phase-2 audit finding #1: async RAG endpoints called sync LLM/DB/Redis
helpers inline, stalling every endpoint of the API for the duration of a
generation. These tests assert the blocking calls execute on a worker
thread (via asyncio.to_thread) while each handler still completes
end-to-end with fully mocked internals (DB-free).
"""

import asyncio
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.rag

# asyncio.run() executes the loop on the calling (main) thread; any
# ident captured inside a fake must differ from this to prove offloading.
_MAIN_THREAD_IDENT = threading.get_ident()


def _run_query(router, query="Explain logs"):
    from backend.src.rag.schemas import RAGQueryRequest

    return asyncio.run(
        router.query(
            request=RAGQueryRequest(query=query),
            req=MagicMock(),
            current_user={"sub": "admin"},
        )
    )


def test_query_offloads_legacy_path_to_worker_thread():
    from backend.src.rag import router
    from backend.src.rag.schemas import RAGQueryResponse

    seen_threads = []

    def fake_legacy(**kwargs):
        seen_threads.append(threading.get_ident())
        return RAGQueryResponse(
            answer="legacy answer",
            sources=[],
            uncertainty_score=0.5,
            confidence_level="medium",
            is_uncertain=False,
            recommendation="Review recommended",
            model_used="legacy-model",
        )

    with (
        patch.object(router, "_check_rate_limit", lambda *a, **k: None),
        patch("backend.src.rag.router.get_cached_response", return_value=None),
        patch.object(router.config, "champion", "legacy"),
        patch.object(router, "_run_legacy_query", fake_legacy),
    ):
        resp = _run_query(router)

    assert resp.answer == "legacy answer"
    assert seen_threads == [seen_threads[0]]
    assert seen_threads[0] != _MAIN_THREAD_IDENT


def test_stats_query_offloads_db_to_worker_thread():
    from backend.src.rag import router

    seen_threads = []

    def recording_get_cursor():
        seen_threads.append(threading.get_ident())
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
        return ctx

    with (
        patch.object(router, "_check_rate_limit", lambda *a, **k: None),
        patch("backend.src.rag.router.get_cached_response", return_value=None),
        patch.object(
            router, "classify_query_type", return_value=router.QueryType.STATS
        ),
        patch.object(router, "get_cursor", recording_get_cursor),
    ):
        resp = _run_query(router, query="how many anomalies")

    assert resp.model_used == "db_stats"
    assert "Total anomalies: 0" in resp.answer
    assert seen_threads == [seen_threads[0]]
    assert seen_threads[0] != _MAIN_THREAD_IDENT


def test_champion_persistence_runs_off_event_loop():
    from backend.src.rag import router

    agent_result = {
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
    seen_threads = []

    def fake_save(**kwargs):
        seen_threads.append(threading.get_ident())
        return 7

    fake_save = MagicMock(side_effect=fake_save)

    with (
        patch.object(router, "_check_rate_limit", lambda *a, **k: None),
        patch("backend.src.rag.router.get_cached_response", return_value=None),
        patch("backend.src.rag.router.set_cached_response"),
        patch("backend.src.rag.router._get_user_id_from_username", return_value=1),
        patch("backend.src.rag.router._save_query_history", fake_save) as spy,
        patch("backend.src.rag.router._save_agent_trace"),
        patch.object(router.config, "champion", "agentic"),
        patch.object(router.config, "champion_fallback", True),
        patch(
            "backend.src.rag.agent.run_agent_query",
            new=AsyncMock(return_value=agent_result),
        ),
    ):
        resp = _run_query(router)

    spy.assert_called_once()
    assert resp.answer == "agent answer"
    assert resp.query_id == 7
    assert seen_threads == [seen_threads[0]]
    assert seen_threads[0] != _MAIN_THREAD_IDENT


def test_run_agent_query_generates_off_event_loop():
    from backend.src.rag import agent

    seen_threads = []

    def fake_generate(query, atm_id, evidence, top_k):
        seen_threads.append(threading.get_ident())
        response = SimpleNamespace(decision_escalations=0, decision_cost_usd=None)
        return response, SimpleNamespace(), []

    fake_cfg = MagicMock()
    fake_cfg.is_configured = True
    fake_cfg.hybrid_top_k = 5
    fake_cfg.agent_grounding_retry_threshold = 0.6
    fake_cfg.agent_max_retries = 1

    fake_graph = SimpleNamespace(ainvoke=AsyncMock(return_value=None))

    with (
        patch.object(agent, "config", fake_cfg),
        patch.object(
            agent, "_get_agentic_graph", new=AsyncMock(return_value=fake_graph)
        ),
        patch.object(agent, "_generate", fake_generate),
        patch.object(
            agent, "_build_result", return_value={"answer": "ok", "sources": [1]}
        ),
        patch.object(agent, "_tracer", MagicMock()),
    ):
        result = asyncio.run(
            agent.run_agent_query(query="Explain logs", mode=agent.AgentMode.AGENTIC)
        )

    assert result["answer"] == "ok"
    assert seen_threads == [seen_threads[0]]
    assert seen_threads[0] != _MAIN_THREAD_IDENT
