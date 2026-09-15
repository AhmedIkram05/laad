"""Phase 4 emit smoke: one no-LLM RAG query lands the full gold-path span tree.

The trace is pinned onto agent._tracer directly: the global TracerProvider
may already be set by another test module and OTel forbids overriding it.
"""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from opentelemetry.trace import StatusCode

from backend.src.rag import agent
from backend.src.rag.agent_types import AgentMode

pytestmark = pytest.mark.rag


@pytest.fixture(autouse=True)
def _clean_graphs():
    agent.reset_graphs()
    yield
    agent.reset_graphs()


@pytest.fixture
def _exporter(monkeypatch):
    exporter = InMemorySpanExporter()
    provider = TracerProvider(resource=Resource.create({"service.name": "unit-smoke"}))
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(agent, "_tracer", provider.get_tracer("laad.rag"))
    return exporter


def test_hybrid_query_emits_root_tool_and_gate(_exporter):
    from backend.src.rag.agent import run_agent_query
    from backend.tests.unit.test_agent_loop import _patch_env

    with _patch_env(script=[]):
        result = asyncio.run(
            run_agent_query(
                "troubleshoot the network timeout anomaly on ATM-GB-0001",
                atm_id="ATM-GB-0001",
                mode=AgentMode.HYBRID,
            )
        )
    assert "error" not in result

    spans = _exporter.get_finished_spans()
    roots = [s for s in spans if s.name == "rag.query"]
    assert len(roots) == 1, "expected exactly one rag.query root span"
    root = roots[0]
    assert root.parent is None
    assert root.attributes["mode"] == "hybrid"

    tools = [s for s in spans if s.name.startswith("rag.tool.")]
    assert tools, "expected at least one rag.tool.<name> child span"
    for tool in tools:
        # Same trace as the root; the immediate parent may be an
        # auto-instrumented langgraph span from the global provider.
        assert tool.context.trace_id == root.context.trace_id
        assert tool.attributes["ok"] is True
        assert tool.attributes["duration_s"] >= 0

    gates = [e for e in root.events if e.name == "rag.gate"]
    assert len(gates) == 1, "expected the rag.gate span event on the root"
    attrs = gates[0].attributes
    from backend.src.rag.uncertainty import (
        CONFIDENCE_HIGH_THRESHOLD,
        CONFIDENCE_MEDIUM_THRESHOLD,
    )

    assert attrs["laad.gate.conf_high"] == CONFIDENCE_HIGH_THRESHOLD
    assert attrs["laad.gate.conf_medium"] == CONFIDENCE_MEDIUM_THRESHOLD
    assert attrs["laad.gate.decision"] == result["confidence_level"]
    assert attrs["laad.gate.confidence"] == result["uncertainty_score"]
    assert attrs["laad.gate.recommendation"] == result["recommendation"]


def test_query_failure_reports_error_on_root(_exporter):
    from backend.src.rag.agent import run_agent_query
    from backend.tests.unit.test_agent_loop import _patch_env

    with _patch_env(script=[], tools=[]):
        with patch(
            "backend.src.rag.generator.get_generator",
            side_effect=RuntimeError("boom"),
        ):
            result = asyncio.run(run_agent_query("q", mode=AgentMode.HYBRID))
    assert "boom" in result["error"]

    spans = _exporter.get_finished_spans()
    roots = [s for s in spans if s.name == "rag.query"]
    assert len(roots) == 1
    root = roots[0]
    assert any(e.name == "exception" for e in root.events)
    assert root.status.status_code == StatusCode.ERROR
