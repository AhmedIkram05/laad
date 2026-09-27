"""Tests for the Phase 2 Jev decision-provider swaps in RAGGenerator.

Covers: kill switch (provider None → existing LLM path byte-identical),
score-type confidence swap, noul sound-gate before critique, optional Jev
citation verifier (RAG_JEV_GROUNDING_CHECK, default off), CircuitOpenError
graceful fallback, decision-cost wiring into the agent trace.
"""

from __future__ import annotations

import contextvars
from dataclasses import asdict
from unittest.mock import ANY, MagicMock, patch

import pytest

from backend.src.rag.decision_client import (
    CircuitOpenError,
    DecisionAnswer,
    DecisionQuestion,
)
from backend.src.rag.generator import (
    DIAGNOSTIC_PROMPT,
    GeneratedResponse,
    QueryType,
    RAGGenerator,
    _check_citations,
)
from backend.src.rag.llm_client import LLMResponse
from backend.src.rag.retriever import RetrievedChunk

pytestmark = pytest.mark.rag

SCORE_COST = 0.000016842
NOUL_COST = 0.00001197


@pytest.fixture
def sample_chunks():
    return [
        RetrievedChunk(
            text="2026-05-15T10:00:00Z [ATM_APP] NETWORK_DISCONNECT: ATM-GB-0001 connection lost | error_code=ERR-0040",
            chunk_id="chunk_1",
            atm_id="ATM-GB-0001",
            timestamp="2026-05-15T10:00:00Z",
            distance=0.1,
            confidence_score=0.9,
        ),
        RetrievedChunk(
            text="2026-05-15T10:01:00Z [KAFKA] ATM-GB-0001 status: Offline | atm_status=Offline, correlation_id=corr-0030",
            chunk_id="chunk_2",
            atm_id="ATM-GB-0001",
            timestamp="2026-05-15T10:01:00Z",
            distance=0.15,
            confidence_score=0.85,
        ),
    ]


def _mock_config(**overrides):
    cfg = MagicMock()
    cfg.reflexion_enabled = False
    cfg.citation_grounding_enabled = False
    cfg.self_consistency_enabled = False
    cfg.jev_escalation_threshold = 0.7
    cfg.jev_grounding_check = False
    cfg.chunk_truncate_length = 800
    cfg.llm_model = "test-model"
    for key, value in overrides.items():
        setattr(cfg, key, value)
    return cfg


def _score_answer(probability=0.72, cost=SCORE_COST):
    return DecisionAnswer(
        name="answer_confidence",
        probability=probability,
        confidence=0.57,
        cost_usd=cost,
        # raw score on the 10-level legend, consistent with the interpolated
        # normalization the generator now reads (score / 9 == probability).
        raw={"type": "score", "score": probability * 9, "confidence": 0.57},
    )


def _noul_answer(probability=0.9, name="response_sound", cost=NOUL_COST):
    return DecisionAnswer(
        name=name,
        probability=probability,
        confidence=0.0,  # observed noul payload omits confidence
        cost_usd=cost,
        raw={"type": "noul", "noul": probability},
    )


def _provider(answers: dict):
    provider = MagicMock()
    provider.decide.return_value = answers
    return provider


@pytest.fixture
def gen_factory(monkeypatch):
    """Kill-switch-safe RAGGenerator factory (get_decision_provider → None)."""
    monkeypatch.setattr(
        "backend.src.rag.generator.get_decision_provider", lambda: None
    )

    def _make(provider=None):
        gen = RAGGenerator()
        gen.llm_client = MagicMock()
        gen.decision_provider = provider
        return gen

    return _make


class TestKillSwitch:
    """Provider None → the existing LLM path is invoked exactly as today."""

    def test_generate_calls_existing_methods_as_today(self, gen_factory, sample_chunks):
        gen = gen_factory()
        gen._compute_self_consistency = MagicMock(return_value=(0.9, ["sample text"]))
        gen._estimate_verbalized_confidence = MagicMock(return_value=0.85)
        gen._critique_response = MagicMock(return_value=None)
        cfg = _mock_config(reflexion_enabled=True, self_consistency_enabled=True)

        with patch("backend.src.rag.generator.config", cfg):
            response = gen.generate("q", sample_chunks)

        expected_context = gen._build_context(sample_chunks, QueryType.DIAGNOSTIC)
        args, kwargs = gen._critique_response.call_args
        assert args == ("q", expected_context, "sample text", DIAGNOSTIC_PROMPT)
        assert kwargs == {}
        conf_args, conf_kwargs = gen._estimate_verbalized_confidence.call_args
        assert conf_args == ("q", expected_context, "sample text", DIAGNOSTIC_PROMPT)
        assert conf_kwargs == {"cost_sink": ANY, "escalation_sink": ANY}
        assert conf_kwargs["cost_sink"] == []
        assert conf_kwargs["escalation_sink"] == []
        assert response.verbalized_confidence == 0.85
        assert response.critique_text is None
        assert response.was_revised is False
        assert response.decision_cost_usd is None
        # Samples path reuses samples[0]; the LLM is only hit by the mocked
        # self-consistency helper, so the raw client is never called here.
        gen.llm_client.generate.assert_not_called()

    def test_estimate_verbalized_confidence_uses_llm_without_provider(self, gen_factory):
        gen = gen_factory()
        gen.llm_client.generate.return_value = LLMResponse(
            text="0.85", raw_response={}, model="m", finish_reason="stop"
        )
        assert gen._estimate_verbalized_confidence("q", "ctx", "a", "sys") == 0.85
        gen.llm_client.generate.assert_called_once()


class TestJevScoreSwap:
    """Verbalized confidence → Jev score question."""

    def test_score_question_replaces_llm_call(self, gen_factory):
        gen = gen_factory()
        provider = _provider({"answer_confidence": _score_answer(0.72)})
        gen.decision_provider = provider
        sink: list[float] = []

        confidence = gen._estimate_verbalized_confidence(
            "q", "ctx", "answer", "sys", cost_sink=sink
        )

        assert confidence == 0.72
        gen.llm_client.generate.assert_not_called()
        assert sink == pytest.approx([SCORE_COST])
        state, questions = provider.decide.call_args.args
        assert "Question:\nq" in state and "Context:\nctx" in state
        assert "Answer:\nanswer" in state
        question = questions["answer_confidence"]
        assert isinstance(question, DecisionQuestion)
        assert question.type == "score"
        assert question.criteria == [f"{level / 10:.1f}" for level in range(10)]

    @pytest.mark.parametrize(
        "raw,expected,threshold",
        [
            # Clamped value above the escalation threshold: Jev answer kept.
            (1.5, 1.0, 0.7),
            # Below-threshold values need threshold 0 to stay on the Jev path
            # (the default threshold escalates them to the LLM — covered by
            # test_rag_decision_cascade.py).
            (0.123456, 0.123, 0.0),
            (0.0, 0.0, 0.0),
        ],
    )
    def test_probability_clamped_and_rounded(
        self, gen_factory, raw, expected, threshold
    ):
        gen = gen_factory()
        gen.decision_provider = _provider({"answer_confidence": _score_answer(raw)})
        cfg = _mock_config(jev_escalation_threshold=threshold)

        with patch("backend.src.rag.generator.config", cfg):
            confidence = gen._estimate_verbalized_confidence("q", "ctx", "a", "sys")

        assert confidence == expected

    def test_score_answer_missing_falls_back_to_llm(self, gen_factory):
        gen = gen_factory()
        gen.decision_provider = _provider({})  # Jev returned no answer
        gen.llm_client.generate.return_value = LLMResponse(
            text="0.85", raw_response={}, model="m", finish_reason="stop"
        )

        confidence = gen._estimate_verbalized_confidence("q", "ctx", "a", "sys")

        assert confidence == 0.85
        gen.decision_provider.decide.assert_called_once()

    def test_generate_propagates_jev_confidence_and_cost(self, gen_factory, sample_chunks):
        gen = gen_factory()
        gen.decision_provider = _provider({"answer_confidence": _score_answer(0.72)})
        gen._compute_self_consistency = MagicMock(return_value=(0.9, ["sample text"]))
        gen.llm_client.generate.return_value = LLMResponse(
            text="unused", raw_response={}, model="m", finish_reason="stop"
        )
        cfg = _mock_config(self_consistency_enabled=True)

        with patch("backend.src.rag.generator.config", cfg):
            response = gen.generate("q", sample_chunks)

        assert response.verbalized_confidence == 0.72
        assert response.decision_cost_usd == pytest.approx(SCORE_COST)


class TestJevSoundGate:
    """Critique → Jev noul sound-gate before the LLM critique."""

    def test_noul_above_threshold_skips_llm_critique(self, gen_factory):
        gen = gen_factory()
        gen.decision_provider = _provider({"response_sound": _noul_answer(0.9)})
        gen._critique_response = MagicMock(return_value="should not be called")
        sink: list[float] = []
        cfg = _mock_config(jev_escalation_threshold=0.7)

        with patch("backend.src.rag.generator.config", cfg):
            critique = gen._critique_with_jev_gate("q", "ctx", "a", "sys", cost_sink=sink)

        assert critique is None
        gen._critique_response.assert_not_called()
        assert sink == pytest.approx([NOUL_COST])
        state, questions = gen.decision_provider.decide.call_args.args
        assert questions["response_sound"].type == "noul"

    def test_noul_at_threshold_is_sound(self, gen_factory):
        gen = gen_factory()
        gen.decision_provider = _provider({"response_sound": _noul_answer(0.7)})
        gen._critique_response = MagicMock()
        cfg = _mock_config(jev_escalation_threshold=0.7)

        with patch("backend.src.rag.generator.config", cfg):
            critique = gen._critique_with_jev_gate("q", "ctx", "a", "sys")

        assert critique is None
        gen._critique_response.assert_not_called()

    def test_noul_below_threshold_runs_llm_critique(self, gen_factory):
        gen = gen_factory()
        gen.decision_provider = _provider({"response_sound": _noul_answer(0.3)})
        gen._critique_response = MagicMock(return_value="claim X lacks evidence")
        sink: list[float] = []
        cfg = _mock_config(jev_escalation_threshold=0.7)

        with patch("backend.src.rag.generator.config", cfg):
            critique = gen._critique_with_jev_gate("q", "ctx", "a", "sys", cost_sink=sink)

        assert critique == "claim X lacks evidence"
        gen._critique_response.assert_called_once_with("q", "ctx", "a", "sys")
        assert sink == pytest.approx([NOUL_COST])

    def test_circuit_open_falls_back_to_llm_critique(self, gen_factory):
        gen = gen_factory()
        gen.decision_provider = MagicMock()
        gen.decision_provider.decide.side_effect = CircuitOpenError("circuit open")
        gen._critique_response = MagicMock(return_value="llm critique")
        cfg = _mock_config()

        with patch("backend.src.rag.generator.config", cfg):
            critique = gen._critique_with_jev_gate("q", "ctx", "a", "sys")

        assert critique == "llm critique"
        gen._critique_response.assert_called_once_with("q", "ctx", "a", "sys")

    def test_decision_error_falls_back_to_llm_critique(self, gen_factory):
        gen = gen_factory()
        gen.decision_provider = MagicMock()
        gen.decision_provider.decide.side_effect = RuntimeError("http 500")
        gen._critique_response = MagicMock(return_value="llm critique")
        cfg = _mock_config()

        with patch("backend.src.rag.generator.config", cfg):
            critique = gen._critique_with_jev_gate("q", "ctx", "a", "sys")

        assert critique == "llm critique"
        gen._critique_response.assert_called_once()

    def test_provider_none_delegates_directly(self, gen_factory):
        gen = gen_factory()  # provider None
        gen._critique_response = MagicMock(return_value="llm critique")

        critique = gen._critique_with_jev_gate("q", "ctx", "a", "sys")

        assert critique == "llm critique"
        gen._critique_response.assert_called_once_with("q", "ctx", "a", "sys")

    def test_generate_skips_llm_critique_when_sound(self, gen_factory, sample_chunks):
        gen = gen_factory()
        gen.decision_provider = _provider({"response_sound": _noul_answer(0.9)})
        gen.llm_client.generate.return_value = LLMResponse(
            text="answer", raw_response={}, model="m", finish_reason="stop"
        )
        cfg = _mock_config(reflexion_enabled=True)

        with patch("backend.src.rag.generator.config", cfg):
            response = gen.generate("q", sample_chunks)

        assert response.critique_text is None
        assert response.was_revised is False
        assert response.decision_cost_usd == pytest.approx(NOUL_COST)
        gen.llm_client.generate.assert_called_once()  # critique + regen skipped

    def test_generate_accumulates_costs_across_jev_calls(self, gen_factory, sample_chunks):
        gen = gen_factory()
        gen.decision_provider = MagicMock()
        gen.decision_provider.decide.side_effect = [
            {"response_sound": _noul_answer(0.3)},  # gate → below threshold
            {"answer_confidence": _score_answer(0.72)},
        ]
        gen._critique_response = MagicMock(return_value=None)
        gen._compute_self_consistency = MagicMock(return_value=(0.9, ["sample text"]))
        gen.llm_client.generate.return_value = LLMResponse(
            text="answer", raw_response={}, model="m", finish_reason="stop"
        )
        cfg = _mock_config(reflexion_enabled=True, self_consistency_enabled=True)

        with patch("backend.src.rag.generator.config", cfg):
            response = gen.generate("q", sample_chunks)

        assert response.decision_cost_usd == pytest.approx(NOUL_COST + SCORE_COST)
        assert gen.decision_provider.decide.call_count == 2


class TestJevGroundingCheck:
    """Optional Jev secondary citation verifier (default OFF)."""

    GROUNDED_ANSWER = (
        "ATM-GB-0001 has error ERR-0040 and also ATM-GB-9999 has error ERR-9999"
    )

    def _run_generate(self, gen, sample_chunks, **cfg_overrides):
        gen.llm_client.generate.return_value = LLMResponse(
            text=self.GROUNDED_ANSWER, raw_response={}, model="m", finish_reason="stop"
        )
        cfg = _mock_config(citation_grounding_enabled=True, **cfg_overrides)
        with patch("backend.src.rag.generator.config", cfg):
            return gen.generate("q", sample_chunks)

    def test_default_off_keeps_entity_overlap_and_skips_jev(
        self, gen_factory, sample_chunks
    ):
        gen = gen_factory()
        gen.decision_provider = MagicMock()  # provider ACTIVE, flag OFF

        response = self._run_generate(gen, sample_chunks)

        assert response.grounding_score == _check_citations(
            self.GROUNDED_ANSWER, sample_chunks
        )
        assert response.grounding_score == pytest.approx(0.5)
        gen.decision_provider.decide.assert_not_called()
        assert response.decision_cost_usd is None

    def test_on_combines_min(self, gen_factory, sample_chunks):
        gen = gen_factory()
        gen.decision_provider = _provider(
            {"citations_grounded": _noul_answer(0.3, name="citations_grounded")}
        )

        response = self._run_generate(gen, sample_chunks, jev_grounding_check=True)

        assert response.grounding_score == pytest.approx(0.3)  # min(0.5, 0.3)
        assert response.decision_cost_usd == pytest.approx(NOUL_COST)
        state, questions = gen.decision_provider.decide.call_args.args
        assert questions["citations_grounded"].type == "noul"
        assert "Answer:\n" in state

    def test_on_jev_higher_keeps_entity_score(self, gen_factory, sample_chunks):
        gen = gen_factory()
        gen.decision_provider = _provider(
            {"citations_grounded": _noul_answer(0.9, name="citations_grounded")}
        )

        response = self._run_generate(gen, sample_chunks, jev_grounding_check=True)

        assert response.grounding_score == pytest.approx(0.5)  # min(0.5, 0.9)

    def test_on_failure_keeps_entity_score(self, gen_factory, sample_chunks):
        gen = gen_factory()
        gen.decision_provider = MagicMock()
        gen.decision_provider.decide.side_effect = RuntimeError("boom")

        response = self._run_generate(gen, sample_chunks, jev_grounding_check=True)

        assert response.grounding_score == pytest.approx(0.5)
        assert response.decision_cost_usd is None


class TestAgentCostWiring:
    """Decision cost/provider flows: GeneratedResponse → AgentTrace → trace dict."""

    def test_generate_accumulates_decision_cost_into_trace(self, monkeypatch):
        from backend.src.rag import agent as agent_module

        trace = agent_module.AgentTrace(mode="agentic")
        monkeypatch.setattr(
            agent_module,
            "_current_trace",
            contextvars.ContextVar("rag_agent_trace_test", default=trace),
        )
        monkeypatch.setattr("backend.src.rag.retriever.get_retriever", lambda: None)
        monkeypatch.setattr(
            "backend.src.rag.generator.get_generator", lambda: MagicMock()
        )
        monkeypatch.setattr(
            "backend.src.rag.uncertainty.get_uncertainty_estimator",
            lambda: MagicMock(),
        )
        monkeypatch.setattr(
            "backend.src.rag.uncertainty.emit_gate_event", MagicMock()
        )
        generator = MagicMock()
        first = GeneratedResponse(
            text="answer", sources=[], model="m", raw_response={},
            decision_cost_usd=0.00005,
        )
        generator.generate.return_value = first
        monkeypatch.setattr("backend.src.rag.generator.get_generator", lambda: generator)

        evidence = [
            {
                "kind": "chunk",
                "content": {"text": "ATM-GB-0001 log line", "chunk_id": "c1"},
                "source_tool": "search_knowledge",
            }
        ]
        agent_module._generate("q", "ATM-GB-0001", evidence, None)

        assert trace.provider == "jev"
        assert trace.cost_usd == pytest.approx(0.00005)

        # Retry round: a second _generate call accumulates instead of overwrite.
        second = GeneratedResponse(
            text="answer 2", sources=[], model="m", raw_response={},
            decision_cost_usd=0.00003,
        )
        generator.generate.return_value = second
        agent_module._generate("q", "ATM-GB-0001", evidence, None)

        assert trace.cost_usd == pytest.approx(0.00008)
        assert trace.provider == "jev"

    def test_no_decision_cost_leaves_trace_untouched(self, monkeypatch):
        from backend.src.rag import agent as agent_module

        trace = agent_module.AgentTrace(mode="agentic")
        monkeypatch.setattr(
            agent_module,
            "_current_trace",
            contextvars.ContextVar("rag_agent_trace_test2", default=trace),
        )
        monkeypatch.setattr("backend.src.rag.retriever.get_retriever", lambda: None)
        monkeypatch.setattr(
            "backend.src.rag.uncertainty.get_uncertainty_estimator",
            lambda: MagicMock(),
        )
        monkeypatch.setattr(
            "backend.src.rag.uncertainty.emit_gate_event", MagicMock()
        )
        generator = MagicMock()
        generator.generate.return_value = GeneratedResponse(
            text="answer", sources=[], model="m", raw_response={}
        )
        monkeypatch.setattr("backend.src.rag.generator.get_generator", lambda: generator)

        evidence = [
            {
                "kind": "chunk",
                "content": {"text": "log line", "chunk_id": "c1"},
                "source_tool": "search_knowledge",
            }
        ]
        agent_module._generate("q", "ATM-GB-0001", evidence, None)

        assert trace.provider is None
        assert trace.cost_usd is None

    def test_agent_trace_defaults_and_asdict_keys(self):
        from backend.src.rag.agent_types import AgentTrace

        trace = AgentTrace(mode="agentic")
        assert trace.provider is None
        assert trace.cost_usd is None
        dumped = asdict(trace)
        assert "provider" in dumped and "cost_usd" in dumped
