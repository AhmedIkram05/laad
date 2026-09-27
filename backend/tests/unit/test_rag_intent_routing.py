"""Phase 4 tests: Jev Choice intent routing + decision.* spans.

Routing: a Jev choice question classifies HYBRID intent first when the
decision provider is active; the deterministic keyword classifier is the
fallback (provider None, decision failure, low confidence, unknown option,
missing answer). Spans: decision.jev fires at every decision call site and
decision.escalations lands on the rag.query root span; tracing failures
never break the decision flow. All decision calls are monkeypatched — no
live API calls in unit tests.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

from backend.src.rag import agent, generator as generator_module
from backend.src.rag.agent_types import AgentMode
from backend.src.rag.decision_client import (
    CircuitOpenError,
    DecisionAnswer,
    DecisionQuestion,
)
from backend.src.rag.generator import RAGGenerator
from backend.src.rag.utils import QueryType, classify_query_type

pytestmark = pytest.mark.rag

SCORE_COST = 0.000016842
NOUL_COST = 0.00001197
CHOICE_COST = 0.000016

PLAN_TOOL = {
    QueryType.STATS: "get_statistics",
    QueryType.DIAGNOSTIC: "get_atm_metrics",
    QueryType.TROUBLESHOOTING: "query_anomalies",
    QueryType.GENERAL: "get_machine_history",
}


def _choice_answer(choice="troubleshooting", confidence=0.9):
    return DecisionAnswer(
        name="query_intent",
        probability=0.9,
        confidence=confidence,
        cost_usd=CHOICE_COST,
        raw={
            "type": "choice",
            "choice": choice,
            "confidence": confidence,
            "probabilities": {choice: 0.9},
        },
    )


def _score_answer(probability=0.72):
    """Score answer whose interpolated legend position == probability."""
    return DecisionAnswer(
        name="answer_confidence",
        probability=probability,
        confidence=0.57,
        cost_usd=SCORE_COST,
        raw={"type": "score", "score": probability * 9, "confidence": 0.57},
    )


def _noul_answer(name, probability=0.9):
    return DecisionAnswer(
        name=name,
        probability=probability,
        confidence=0.8,
        cost_usd=NOUL_COST,
        raw={"type": "noul", "noul": probability},
    )


class _ExplodingTracer:
    """Tracer whose span creation raises (simulates a broken OTel stack)."""

    def start_as_current_span(self, *args, **kwargs):
        raise RuntimeError("otel exporter down")


def _sdk_exporter(monkeypatch, module):
    """Patch module._tracer onto a real SDK tracer + in-memory exporter."""
    exporter = InMemorySpanExporter()
    provider = TracerProvider(
        resource=Resource.create({"service.name": "unit-decision"})
    )
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(module, "_tracer", provider.get_tracer("laad.rag"))
    return exporter


def _stub_config(threshold=0.55):
    cfg = MagicMock()
    cfg.jev_escalation_threshold = threshold
    cfg.jev_model = "jev-test-model"
    return cfg


@pytest.fixture(autouse=True)
def _fresh_routing_state():
    """Clear cached graphs + the cached intent provider around each test."""
    agent.reset_graphs()
    yield
    agent.reset_graphs()


# --------------------------------------------------------------------------
# Intent routing
# --------------------------------------------------------------------------
class TestJevIntentRouting:
    @pytest.fixture
    def _cfg(self, monkeypatch):
        monkeypatch.setattr(agent, "config", _stub_config())

    @pytest.fixture
    def _provider_seam(self, monkeypatch):
        """get_decision_provider patched per-test; fresh cache seam."""
        monkeypatch.setattr(agent, "_intent_provider", None)
        return monkeypatch

    @pytest.mark.parametrize(
        "choice,expected",
        [
            ("stats", QueryType.STATS),
            ("diagnostic", QueryType.DIAGNOSTIC),
            ("troubleshooting", QueryType.TROUBLESHOOTING),
            ("general", QueryType.GENERAL),
        ],
    )
    def test_each_valid_option_routes(self, _cfg, _provider_seam, choice, expected):
        provider = MagicMock()
        provider.decide.return_value = {"query_intent": _choice_answer(choice)}
        _provider_seam.setattr(agent, "get_decision_provider", lambda: provider)

        result = agent._classify_intent("anything at all")

        assert result is expected
        provider.decide.assert_called_once()
        state, questions = provider.decide.call_args[0]
        assert state == "anything at all"
        question = questions["query_intent"]
        assert question.type == "choice"
        assert question.options == [qt.value for qt in QueryType]
        assert set(question.criteria) == set(question.options)

    @pytest.mark.parametrize(
        "choice,expected",
        [
            ("stats", "get_statistics"),
            ("diagnostic", "get_atm_metrics"),
            ("troubleshooting", "query_anomalies"),
            ("general", "get_machine_history"),
        ],
    )
    def test_plan_tools_follows_jev_choice(
        self, _cfg, _provider_seam, choice, expected
    ):
        provider = MagicMock()
        provider.decide.return_value = {"query_intent": _choice_answer(choice)}
        _provider_seam.setattr(agent, "get_decision_provider", lambda: provider)

        plan = agent._plan_tools("how to fix the printer", None)

        assert plan == ["search_knowledge", expected]

    def test_jev_overrides_deterministic_classification(self, _cfg, _provider_seam):
        """'how to fix' is deterministically troubleshooting; Jev says stats."""
        provider = MagicMock()
        provider.decide.return_value = {"query_intent": _choice_answer("stats")}
        _provider_seam.setattr(agent, "get_decision_provider", lambda: provider)

        plan = agent._plan_tools("how to fix the printer", None)

        assert plan == ["search_knowledge", "get_statistics"]
        assert classify_query_type("how to fix the printer") is (
            QueryType.TROUBLESHOOTING
        )

    def test_option_mapping_is_case_tolerant(self, _cfg, _provider_seam):
        provider = MagicMock()
        provider.decide.return_value = {
            "query_intent": _choice_answer("Troubleshooting")
        }
        _provider_seam.setattr(agent, "get_decision_provider", lambda: provider)

        assert agent._classify_intent("q") is QueryType.TROUBLESHOOTING

    def test_low_confidence_falls_back_to_deterministic(self, _cfg, _provider_seam):
        provider = MagicMock()
        provider.decide.return_value = {
            "query_intent": _choice_answer("stats", confidence=0.1)
        }
        _provider_seam.setattr(agent, "get_decision_provider", lambda: provider)

        result = agent._classify_intent("how many anomalies")

        assert result is None  # deterministic classifier takes over
        provider.decide.assert_called_once()  # Jev was still consulted

    def test_unexpected_option_falls_back(self, _cfg, _provider_seam):
        provider = MagicMock()
        provider.decide.return_value = {
            "query_intent": _choice_answer("weather_forecast")
        }
        _provider_seam.setattr(agent, "get_decision_provider", lambda: provider)

        assert agent._classify_intent("q") is None

    def test_decision_exception_falls_back(self, _cfg, _provider_seam):
        provider = MagicMock()
        provider.decide.side_effect = CircuitOpenError("circuit open")
        _provider_seam.setattr(agent, "get_decision_provider", lambda: provider)

        assert agent._classify_intent("q") is None

    def test_missing_answer_falls_back(self, _cfg, _provider_seam):
        provider = MagicMock()
        provider.decide.return_value = {}
        _provider_seam.setattr(agent, "get_decision_provider", lambda: provider)

        assert agent._classify_intent("q") is None

    def test_provider_none_keeps_deterministic_path_byte_identical(
        self, _cfg, _provider_seam
    ):
        """Kill switch (default): today's path, no Jev call at all."""
        get_provider = MagicMock(return_value=None)
        _provider_seam.setattr(agent, "get_decision_provider", get_provider)

        for query in (
            "how many anomalies are active",
            "why is ATM-GB-0001 failing",
            "how to fix the card reader",
            "summarize the fleet",
        ):
            expected_tool = PLAN_TOOL[classify_query_type(query)]
            assert agent._plan_tools(query, None) == [
                "search_knowledge",
                expected_tool,
            ]

        get_provider.assert_called()  # provider lookup happened
        # no client object was ever constructed, so decide was never called

    def test_provider_cached_across_queries(self, _cfg, _provider_seam):
        """One provider instance (circuit breaker state survives queries)."""
        provider = MagicMock()
        provider.decide.return_value = {"query_intent": _choice_answer("stats")}
        _provider_seam.setattr(agent, "get_decision_provider", lambda: provider)

        agent._classify_intent("q1")
        agent._classify_intent("q2")

        provider.decide.assert_called()
        assert provider.decide.call_count == 2


# --------------------------------------------------------------------------
# Agent-side decision.* spans
# --------------------------------------------------------------------------
class TestAgentDecisionSpans:
    @pytest.fixture
    def _cfg(self, monkeypatch):
        monkeypatch.setattr(agent, "config", _stub_config())

    @pytest.fixture
    def _provider_seam(self, monkeypatch):
        monkeypatch.setattr(agent, "_intent_provider", None)
        return monkeypatch

    @pytest.fixture
    def _exporter(self, monkeypatch):
        return _sdk_exporter(monkeypatch, agent)

    def test_intent_span_attributes_when_routed_jev(
        self, _cfg, _provider_seam, _exporter
    ):
        provider = MagicMock()
        provider.decide.return_value = {
            "query_intent": _choice_answer("troubleshooting")
        }
        _provider_seam.setattr(agent, "get_decision_provider", lambda: provider)

        agent._classify_intent("q")

        spans = [s for s in _exporter.get_finished_spans() if s.name == "decision.jev"]
        assert len(spans) == 1
        attrs = spans[0].attributes
        assert attrs["decision.provider"] == "jev"
        assert attrs["decision.model"] == "jev-test-model"
        assert attrs["decision.question_name"] == "query_intent"
        assert attrs["decision.type"] == "choice"
        assert attrs["decision.confidence"] == pytest.approx(0.9)
        assert attrs["decision.cost_usd"] == pytest.approx(CHOICE_COST)
        assert attrs["decision.routed"] == "jev"
        assert attrs["decision.latency_ms"] >= 0

    def test_intent_span_routed_deterministic_on_failure(
        self, _cfg, _provider_seam, _exporter
    ):
        provider = MagicMock()
        provider.decide.side_effect = CircuitOpenError("circuit open")
        _provider_seam.setattr(agent, "get_decision_provider", lambda: provider)

        assert agent._classify_intent("q") is None

        spans = [s for s in _exporter.get_finished_spans() if s.name == "decision.jev"]
        assert len(spans) == 1
        attrs = spans[0].attributes
        assert attrs["decision.routed"] == "deterministic"
        assert "decision.probability" not in attrs

    def test_intent_span_routed_deterministic_low_confidence(
        self, _cfg, _provider_seam, _exporter
    ):
        provider = MagicMock()
        provider.decide.return_value = {
            "query_intent": _choice_answer("stats", confidence=0.1)
        }
        _provider_seam.setattr(agent, "get_decision_provider", lambda: provider)

        assert agent._classify_intent("q") is None

        spans = [s for s in _exporter.get_finished_spans() if s.name == "decision.jev"]
        assert spans[0].attributes["decision.routed"] == "deterministic"

    def test_no_decision_span_when_provider_none(self, _cfg, _provider_seam, _exporter):
        _provider_seam.setattr(agent, "get_decision_provider", lambda: None)

        agent._classify_intent("q")

        spans = [s for s in _exporter.get_finished_spans() if s.name == "decision.jev"]
        assert spans == []

    def test_intent_survives_raising_tracer(self, _cfg, _provider_seam, monkeypatch):
        monkeypatch.setattr(agent, "_tracer", _ExplodingTracer())
        provider = MagicMock()
        provider.decide.return_value = {"query_intent": _choice_answer("stats")}
        _provider_seam.setattr(agent, "get_decision_provider", lambda: provider)

        assert agent._classify_intent("q") is QueryType.STATS

    def test_root_span_carries_escalation_count(self, _exporter):
        from backend.src.rag.agent import run_agent_query
        from backend.tests.unit.test_agent_loop import _patch_env

        response = SimpleNamespace(
            text="Answer",
            model="fake-model",
            self_consistency_score=0.95,
            verbalized_confidence=0.9,
            grounding_score=0.9,
            cross_encoder_used=False,
            was_revised=False,
            critique_text=None,
            decision_cost_usd=CHOICE_COST,
            decision_escalations=2,
        )
        fake_generator = MagicMock()
        fake_generator.generate.return_value = response

        with (
            _patch_env(script=[]),
            patch(
                "backend.src.rag.generator.get_generator",
                return_value=fake_generator,
            ),
        ):
            result = asyncio.run(
                run_agent_query(
                    "troubleshoot the timeout anomaly",
                    mode=AgentMode.HYBRID,
                )
            )
        assert "error" not in result

        roots = [s for s in _exporter.get_finished_spans() if s.name == "rag.query"]
        assert roots[0].attributes["decision.escalations"] == 2

    def test_root_span_escals_default_zero_without_field(self, _exporter):
        """The agent-loop fake generator has no decision fields: default 0."""
        from backend.src.rag.agent import run_agent_query
        from backend.tests.unit.test_agent_loop import _patch_env

        with _patch_env(script=[]):
            result = asyncio.run(
                run_agent_query(
                    "troubleshoot the timeout anomaly",
                    mode=AgentMode.HYBRID,
                )
            )
        assert "error" not in result

        roots = [s for s in _exporter.get_finished_spans() if s.name == "rag.query"]
        assert roots[0].attributes["decision.escalations"] == 0


# --------------------------------------------------------------------------
# Generator-side decision.* spans
# --------------------------------------------------------------------------
@pytest.fixture
def gcfg(monkeypatch):
    cfg = MagicMock()
    cfg.reflexion_enabled = False
    cfg.citation_grounding_enabled = False
    cfg.self_consistency_enabled = False
    cfg.jev_escalation_threshold = 0.55
    cfg.jev_grounding_check = False
    cfg.jev_model = "jev-test-model"
    cfg.chunk_truncate_length = 800
    monkeypatch.setattr("backend.src.rag.generator.config", cfg)
    return cfg


@pytest.fixture
def gen_factory(monkeypatch):
    monkeypatch.setattr("backend.src.rag.generator.get_decision_provider", lambda: None)

    def _make(provider=None):
        gen = RAGGenerator()
        gen.llm_client = MagicMock()
        gen.decision_provider = provider
        return gen

    return _make


class TestGeneratorDecisionSpans:
    @pytest.fixture
    def _exporter(self, monkeypatch):
        return _sdk_exporter(monkeypatch, generator_module)

    def _decision_spans(self, _exporter):
        return [s for s in _exporter.get_finished_spans() if s.name == "decision.jev"]

    def test_confidence_span_marks_escalation(self, gen_factory, gcfg, _exporter):
        gen = gen_factory(
            MagicMock(
                decide=MagicMock(return_value={"answer_confidence": _score_answer(0.4)})
            )
        )
        gen._llm_verbalized_confidence = MagicMock(return_value=0.85)

        result = gen._estimate_verbalized_confidence(
            "q", "ctx", "a", "sys", escalation_sink=[]
        )

        assert result == 0.85
        attrs = self._decision_spans(_exporter)[0].attributes
        assert attrs["decision.type"] == "score"
        assert attrs["decision.question_name"] == "answer_confidence"
        assert attrs["decision.escalated"] is True
        assert attrs["decision.probability"] == pytest.approx(0.4)
        assert attrs["decision.cost_usd"] == pytest.approx(SCORE_COST)
        assert attrs["decision.model"] == "jev-test-model"
        assert attrs["decision.latency_ms"] >= 0

    def test_confidence_span_not_escalated(self, gen_factory, gcfg, _exporter):
        gen = gen_factory(
            MagicMock(
                decide=MagicMock(return_value={"answer_confidence": _score_answer(0.9)})
            )
        )
        gen._llm_verbalized_confidence = MagicMock()

        result = gen._estimate_verbalized_confidence("q", "ctx", "a", "sys")

        assert result == pytest.approx(0.9)
        attrs = self._decision_spans(_exporter)[0].attributes
        assert attrs["decision.escalated"] is False

    def test_decision_failure_span_without_probability(
        self, gen_factory, gcfg, _exporter
    ):
        provider = MagicMock()
        provider.decide.side_effect = RuntimeError("boom")
        gen = gen_factory(provider)
        gen._llm_verbalized_confidence = MagicMock(return_value=0.6)

        result = gen._estimate_verbalized_confidence("q", "ctx", "a", "sys")

        assert result == 0.6  # graceful degradation to the LLM path
        attrs = self._decision_spans(_exporter)[0].attributes
        assert "decision.probability" not in attrs
        assert attrs["decision.question_name"] == "answer_confidence"
        assert "decision.escalated" not in attrs

    def test_sound_gate_span(self, gen_factory, gcfg, _exporter):
        gen = gen_factory(
            MagicMock(
                decide=MagicMock(
                    return_value={"response_sound": _noul_answer("response_sound", 0.9)}
                )
            )
        )
        gen._critique_response = MagicMock()

        result = gen._critique_with_jev_gate("q", "ctx", "a", "sys")

        assert result is None  # sound → LLM critique skipped
        gen._critique_response.assert_not_called()
        attrs = self._decision_spans(_exporter)[0].attributes
        assert attrs["decision.type"] == "noul"
        assert attrs["decision.question_name"] == "response_sound"
        assert attrs["decision.probability"] == pytest.approx(0.9)
        assert "decision.escalated" not in attrs

    def test_grounding_span(self, gen_factory, gcfg, _exporter):
        gen = gen_factory(
            MagicMock(
                decide=MagicMock(
                    return_value={
                        "citations_grounded": _noul_answer("citations_grounded", 0.8)
                    }
                )
            )
        )
        cost_sink: list[float] = []

        result = gen._jev_grounding_score("ctx", "a", cost_sink=cost_sink)

        assert result == pytest.approx(0.8)
        assert cost_sink == pytest.approx([NOUL_COST])
        attrs = self._decision_spans(_exporter)[0].attributes
        assert attrs["decision.type"] == "noul"
        assert attrs["decision.question_name"] == "citations_grounded"

    def test_generator_survives_raising_tracer(self, gen_factory, gcfg, monkeypatch):
        monkeypatch.setattr(generator_module, "_tracer", _ExplodingTracer())
        gen = gen_factory(
            MagicMock(
                decide=MagicMock(return_value={"answer_confidence": _score_answer(0.9)})
            )
        )

        result = gen._estimate_verbalized_confidence("q", "ctx", "a", "sys")

        assert result == pytest.approx(0.9)


# --------------------------------------------------------------------------
# Benchmark/calibration scripts stay monkeypatched (no live calls) — already
# covered by TestBenchmarkRunMonkeypatched in test_rag_decision_cascade.py;
# this file only asserts the seam still exists.
# --------------------------------------------------------------------------
class TestNoLiveCalls:
    def test_decision_question_is_offline_constructible(self):
        """Choice questions carry options + criteria (System One 422 guard)."""
        question = DecisionQuestion(
            name="query_intent",
            type="choice",
            instructions="Pick one.",
            options=[qt.value for qt in QueryType],
            criteria=agent._INTENT_CRITERIA,
        )
        assert question.options and question.criteria

    def test_run_ragas_cache_signature_includes_decision_config(self):
        """Stale-cache trap: the eval cache must key on decision-provider config.

        Asserted via source text (importing run_ragas drags ragas into the
        unit suite).
        """
        from pathlib import Path

        source = (Path(__file__).parents[1] / "eval" / "run_ragas.py").read_text()
        assert '"RAG_DECISION_PROVIDER"' in source
        assert '"RAG_JEV_ESCALATION_THRESHOLD"' in source
