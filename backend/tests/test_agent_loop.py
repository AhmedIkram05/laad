"""Phase 3 tests: agent loop (AGENTIC + HYBRID), evidence fusion, D13, caps."""
from __future__ import annotations

import asyncio
import json
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import StructuredTool

from backend.src.rag.agent import reset_graphs, run_agent_query
from backend.src.rag.agent_types import AgentMode

pytestmark = [pytest.mark.rag]


# --------------------------------------------------------------------------
# Fakes
# --------------------------------------------------------------------------
class _ScriptedModel(BaseChatModel):
    """Returns scripted AIMessages; final response when script exhausted."""

    model_name: str = "fake-model"

    @property
    def _llm_type(self) -> str:
        return "fake-scripted"

    def __init__(self, script):
        super().__init__()
        self._script = list(script)

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        if self._script:
            msg = self._script.pop(0)
        else:
            msg = AIMessage(content="Final answer based on retrieved evidence.")
        return ChatResult(generations=[ChatGeneration(message=msg)])


def _make_tool(name, payload):
    return StructuredTool.from_function(
        func=lambda **kw: json.dumps(payload),
        name=name,
        description=f"Fake {name}",
    )


def _fake_config(**overrides):
    cfg = MagicMock()
    cfg.is_configured = True
    cfg.llm_model = "fake-model"
    cfg.llm_api_key = "k"
    cfg.llm_base_url = "http://fake"
    cfg.temperature = 0.1
    cfg.agent_max_llm_calls = 24
    cfg.agent_grounding_retry_threshold = 0.6
    cfg.agent_max_retries = 1
    cfg.hybrid_top_k = 5
    cfg.reflexion_enabled = False
    cfg.citation_grounding_enabled = False
    cfg.self_consistency_enabled = False
    for k, v in overrides.items():
        setattr(cfg, k, v)
    return cfg


def _fake_generator(grounding_script):
    gen = MagicMock()

    def generate(query, chunks, **kwargs):
        score = grounding_script.pop(0) if grounding_script else 0.9
        return SimpleNamespace(
            text=f"Answer for {query}",
            sources=chunks,
            model="fake-model",
            self_consistency_score=0.95,
            verbalized_confidence=0.9,
            grounding_score=score,
            generation_variance=0.01,
            cross_encoder_used=False,
            was_revised=False,
            critique_text="critique hint",
        )

    gen.generate.side_effect = generate
    return gen


def _fake_uncertainty():
    est = MagicMock()
    est.estimate.return_value = SimpleNamespace(
        final_confidence=0.92,
        confidence_level="high",
        is_uncertain=False,
        recommendation="ok",
        generation_variance=None,
    )
    return est


@contextmanager
def _patch_env(script=None, grounding=None, tools=None, **cfg_overrides):
    """Starts all fakes; restores on exit."""
    script = script if script is not None else [
        AIMessage(content="", tool_calls=[
            {"name": "search_knowledge", "args": {"query": "q", "top_k": 5}, "id": "c1", "type": "tool_call"}
        ]),
        AIMessage(content="Final answer based on retrieved evidence."),
    ]
    if grounding is None:
        grounding = [0.9]
    tools = tools if tools is not None else [
        _make_tool("search_knowledge", {"chunks": [{"text": "chunk text", "chunk_id": "chunk-1", "atm_id": "ATM-GB-0001", "timestamp": "2026-01-01T00:00:00Z", "confidence_score": 0.9}], "count": 1}),
        _make_tool("query_anomalies", {"count": 1, "rows": [{"id": 1, "detected_at": "2026-01-01T00:00:00Z", "atm_id": "ATM-GB-0001", "anomaly_type": "A4", "severity": "ERROR", "title": "Restart loop", "model_confidence_score": 0.8}]}),
    ]
    patches = [
        patch("backend.src.rag.agent.config", _fake_config(**cfg_overrides)),
        patch("backend.src.rag.agent._chat_model", return_value=_ScriptedModel(script)),
        patch("backend.src.mcp.adapter.get_langchain_tools", AsyncMock(return_value=tools)),
        patch("backend.src.rag.generator.get_generator", return_value=_fake_generator(grounding)),
        patch("backend.src.rag.uncertainty.get_uncertainty_estimator", return_value=_fake_uncertainty()),
    ]
    for p in patches:
        p.start()
    try:
        yield
    finally:
        for p in patches:
            p.stop()


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def _clean_graphs():
    reset_graphs()
    yield
    reset_graphs()


# --------------------------------------------------------------------------
# Tests
# --------------------------------------------------------------------------
class TestAgenticLoop:
    def test_runs_tools_and_synthesizes(self):
        with _patch_env():
            result = _run(run_agent_query("What happened on ATM-GB-0001?", atm_id="ATM-GB-0001"))
        assert result["answer"] == "Answer for What happened on ATM-GB-0001?"
        assert result["sources"], "expected at least one source"
        trace = result["agent_trace"]
        assert len(trace["tool_calls"]) == 1
        assert trace["tool_calls"][0]["tool"] == "search_knowledge"
        assert trace["rounds"] == 1
        assert trace["model_calls"] == 2
        assert set(trace["latencies"]) == {"planning_s", "tools_s", "generation_s", "reflexion_s", "total"}

    def test_trace_shape(self):
        with _patch_env():
            result = _run(run_agent_query("q", atm_id="ATM-GB-0001"))
        trace = result["agent_trace"]
        assert trace["mode"] == "agentic"
        assert trace["retries"] == 0
        assert trace["retry_trigger"] is None
        assert trace["model_calls_truncated"] is False
        tc = trace["tool_calls"][0]
        assert tc["ok"] is True
        assert tc["char_len"] > 0
        assert tc["duration_s"] >= 0


class TestHybridLoop:
    def test_runs_planned_pair(self):
        with _patch_env(script=[]):
            result = _run(run_agent_query("troubleshoot the network timeout anomaly on ATM-GB-0001", atm_id="ATM-GB-0001", mode=AgentMode.HYBRID))
        trace = result["agent_trace"]
        assert trace["mode"] == "hybrid"
        assert trace["model_calls"] == 0
        names = [c["tool"] for c in trace["tool_calls"]]
        assert names == trace["selected_tools"]
        assert names == ["search_knowledge", "query_anomalies"]

    def test_row_evidence_converted(self):
        with _patch_env(script=[]):
            result = _run(run_agent_query("troubleshoot the network timeout anomaly on ATM-GB-0001", atm_id="ATM-GB-0001", mode=AgentMode.HYBRID))
        row_sources = [s for s in result["sources"] if s["chunk_id"].startswith("row:")]
        assert row_sources, "expected row-derived sources"
        assert any("A4" in s["text"] for s in row_sources)


class TestD13Retry:
    def test_retries_exactly_once_on_weak_grounding(self):
        with _patch_env(grounding=[0.4, 0.9]):
            result = _run(run_agent_query("q", atm_id="ATM-GB-0001"))
        trace = result["agent_trace"]
        assert trace["retries"] == 1
        assert trace["retry_trigger"] == 0.4
        assert trace["rounds"] == 2

    def test_no_retry_when_grounding_none(self):
        with _patch_env(grounding=[None]):
            result = _run(run_agent_query("q", atm_id="ATM-GB-0001"))
        trace = result["agent_trace"]
        assert trace["retries"] == 0
        assert result["grounding_score"] is None

    def test_hybrid_never_retries(self):
        with _patch_env(script=[], grounding=[0.3]):
            result = _run(run_agent_query("q", atm_id="ATM-GB-0001", mode=AgentMode.HYBRID))
        assert result["agent_trace"]["retries"] == 0


class TestCapsAndConfig:
    def test_cap_sets_truncated_flag(self):
        tool_msg = AIMessage(content="", tool_calls=[
            {"name": "search_knowledge", "args": {"query": "q"}, "id": "c1", "type": "tool_call"}
        ])
        # two tool rounds (hits the cap) then the model synthesizes
        with _patch_env(script=[tool_msg, tool_msg, AIMessage(content="done")], agent_max_llm_calls=2):
            result = _run(run_agent_query("q", atm_id="ATM-GB-0001"))
        assert "error" not in result
        assert result["agent_trace"]["model_calls_truncated"] is True

    def test_not_configured_returns_error(self):
        with _patch_env(is_configured=False):
            result = _run(run_agent_query("q"))
        assert "error" in result
        assert result["answer"] == "I encountered an error processing your request."