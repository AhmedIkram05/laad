"""Tests for the Phase 3 Jev escalation cascade, tau sweep, and 3-arm benchmark.

Covers: SWAP 1 escalation (Jev primary, below-threshold → existing LLM path),
escalation counting on GeneratedResponse, kill-switch invariance, sweep math,
score-semantics normalization comparison, cascade simulation, and the
benchmark main flow (fully monkeypatched — no live calls in tests).
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from backend.src.rag.decision_client import (
    CircuitOpenError,
    DecisionAnswer,
)
from backend.src.rag.generator import GeneratedResponse, RAGGenerator
from backend.src.rag.llm_client import LLMResponse
from backend.src.rag.retriever import RetrievedChunk
from backend.tests.eval.decision_benchmark import (
    arm_metrics,
    simulate_cascade,
)
from backend.tests.eval.decision_calibration import (
    _score_interpolated,
    score_semantics,
    tau_sweep_table,
)

pytestmark = pytest.mark.rag

SCORE_COST = 0.000016842
NOUL_COST = 0.00001197
LLM_CALL_COST = 0.0004


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


class TestEscalationCascade:
    """SWAP 1 cascade: Jev primary, below-threshold → existing LLM path."""

    def test_confidence_uses_interpolated_legend_score(self, gen_factory):
        """Interpolated raw score wins over top-level certainty (calibration)."""
        gen = gen_factory()
        # .probability says 0.19 (top-level certainty of a smeared distribution)
        # but the interpolated legend position says 0.8.
        answer = DecisionAnswer(
            name="answer_confidence",
            probability=0.19,
            confidence=0.0,
            cost_usd=SCORE_COST,
            raw={"type": "score", "score": 7.2, "confidence": 0.0},
        )
        gen.decision_provider = _provider({"answer_confidence": answer})
        gen._llm_verbalized_confidence = MagicMock()

        result = gen._estimate_verbalized_confidence("q", "ctx", "a", "sys")

        assert result == pytest.approx(0.8)  # 7.2 / 9
        gen._llm_verbalized_confidence.assert_not_called()  # 0.8 >= 0.7

    def test_confidence_falls_back_to_probability_without_score(self, gen_factory):
        gen = gen_factory()
        answer = DecisionAnswer(
            name="answer_confidence",
            probability=0.9,
            confidence=0.0,
            cost_usd=SCORE_COST,
            raw={"type": "score"},  # no score field
        )
        gen.decision_provider = _provider({"answer_confidence": answer})

        result = gen._estimate_verbalized_confidence("q", "ctx", "a", "sys")

        assert result == pytest.approx(0.9)

    def test_escalates_below_threshold_and_uses_llm_result(self, gen_factory):
        gen = gen_factory()
        gen.decision_provider = _provider({"answer_confidence": _score_answer(0.4)})
        gen._llm_verbalized_confidence = MagicMock(return_value=0.85)
        sink: list[int] = []

        result = gen._estimate_verbalized_confidence(
            "q", "ctx", "a", "sys", escalation_sink=sink
        )

        assert result == 0.85  # LLM result, not Jev's 0.4
        gen._llm_verbalized_confidence.assert_called_once_with("q", "ctx", "a", "sys")
        assert sink == [1]  # escalation counted

    def test_no_escalation_at_or_above_threshold(self, gen_factory):
        gen = gen_factory()
        for probability in (0.7, 0.9):  # >= tau (0.7) keeps the Jev answer
            gen.decision_provider = _provider(
                {"answer_confidence": _score_answer(probability)}
            )
            gen._llm_verbalized_confidence = MagicMock()
            sink: list[int] = []

            result = gen._estimate_verbalized_confidence(
                "q", "ctx", "a", "sys", escalation_sink=sink
            )

            assert result == pytest.approx(probability)
            gen._llm_verbalized_confidence.assert_not_called()
            assert sink == []

    def test_jev_failure_uses_llm_without_counting_escalation(self, gen_factory):
        gen = gen_factory()
        provider = MagicMock()
        provider.decide.side_effect = CircuitOpenError("circuit open")
        gen.decision_provider = provider
        gen._llm_verbalized_confidence = MagicMock(return_value=0.6)
        sink: list[int] = []

        result = gen._estimate_verbalized_confidence(
            "q", "ctx", "a", "sys", escalation_sink=sink
        )

        assert result == 0.6
        gen._llm_verbalized_confidence.assert_called_once_with("q", "ctx", "a", "sys")
        assert sink == []  # a fallback is not an escalation

    def test_missing_jev_answer_uses_llm_without_counting(self, gen_factory):
        gen = gen_factory()
        gen.decision_provider = _provider({})  # Jev returned no answer
        gen._llm_verbalized_confidence = MagicMock(return_value=0.55)
        sink: list[int] = []

        result = gen._estimate_verbalized_confidence(
            "q", "ctx", "a", "sys", escalation_sink=sink
        )

        assert result == 0.55
        gen._llm_verbalized_confidence.assert_called_once()
        assert sink == []

    def test_provider_none_is_byte_identical_llm_path(self, gen_factory):
        gen = gen_factory()
        gen.llm_client.generate.return_value = LLMResponse(
            text="0.85", raw_response={}, model="m", finish_reason="stop"
        )
        gen._llm_verbalized_confidence = MagicMock(
            wraps=gen._llm_verbalized_confidence
        )
        sink: list[int] = []

        result = gen._estimate_verbalized_confidence(
            "q", "ctx", "a", "sys", escalation_sink=sink
        )

        assert result == 0.85
        gen._llm_verbalized_confidence.assert_called_once_with("q", "ctx", "a", "sys")
        gen.llm_client.generate.assert_called_once()
        assert sink == []

    def test_llm_cost_recorded_in_cost_sink(self, gen_factory):
        gen = gen_factory()
        gen.llm_client.generate.return_value = LLMResponse(
            text="0.85", raw_response={}, model="m", finish_reason="stop",
            cost_usd=LLM_CALL_COST,
        )
        cost_sink: list[float] = []

        result = gen._llm_verbalized_confidence(
            "q", "ctx", "a", "sys", cost_sink=cost_sink
        )

        assert result == 0.85
        assert cost_sink == pytest.approx([LLM_CALL_COST])

    def test_generate_surfaces_escalation_count(self, gen_factory, sample_chunks):
        gen = gen_factory()
        gen.decision_provider = _provider({"answer_confidence": _score_answer(0.4)})
        gen._llm_verbalized_confidence = MagicMock(return_value=0.85)
        gen._compute_self_consistency = MagicMock(return_value=(0.9, ["sample text"]))
        cfg = _mock_config(self_consistency_enabled=True)

        with patch("backend.src.rag.generator.config", cfg):
            response = gen.generate("q", sample_chunks)

        assert isinstance(response, GeneratedResponse)
        assert response.verbalized_confidence == 0.85
        assert response.decision_escalations == 1
        assert response.decision_cost_usd == pytest.approx(SCORE_COST)

    def test_generate_zero_escalations_when_jev_confident(
        self, gen_factory, sample_chunks
    ):
        gen = gen_factory()
        gen.decision_provider = _provider({"answer_confidence": _score_answer(0.9)})
        gen._compute_self_consistency = MagicMock(return_value=(0.9, ["sample text"]))
        cfg = _mock_config(self_consistency_enabled=True)

        with patch("backend.src.rag.generator.config", cfg):
            response = gen.generate("q", sample_chunks)

        assert response.verbalized_confidence == 0.9
        assert response.decision_escalations == 0

    def test_generate_escalation_field_defaults_zero(self):
        response = GeneratedResponse(
            text="t", sources=[], model="m", raw_response={}
        )
        assert response.decision_escalations == 0
        assert response.decision_cost_usd is None


class TestTauSweepMath:
    """Sweep math on synthetic probabilities (offline, no API)."""

    CONFS = [0.9, 0.5, 0.65, 0.2]
    JEV_COST = 1.6e-05
    LLM_COST = 0.0004

    def test_sweep_thresholds_cover_050_to_095(self):
        table = tau_sweep_table(self.CONFS, self.JEV_COST, self.LLM_COST)
        taus = [row["tau"] for row in table]
        assert taus == [0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95]

    def test_escalation_and_agreement_rates(self):
        table = tau_sweep_table(self.CONFS, self.JEV_COST, self.LLM_COST)
        by_tau = {row["tau"]: row for row in table}
        # conf < 0.5 → only 0.2 escalates
        assert by_tau[0.5]["escalated_items"] == 1
        assert by_tau[0.5]["escalation_rate"] == pytest.approx(0.25)
        assert by_tau[0.5]["agreement_rate"] == pytest.approx(0.75)
        # conf < 0.7 → 0.5, 0.65, 0.2 escalate
        assert by_tau[0.7]["escalation_rate"] == pytest.approx(0.75)
        # conf < 0.95 → all escalate
        assert by_tau[0.95]["escalation_rate"] == pytest.approx(1.0)
        assert by_tau[0.95]["agreement_rate"] == pytest.approx(0.0)

    def test_cost_ratio_math(self):
        table = tau_sweep_table(self.CONFS, self.JEV_COST, self.LLM_COST)
        by_tau = {row["tau"]: row for row in table}
        n = len(self.CONFS)
        row = by_tau[0.7]
        expected_cascade = n * self.JEV_COST + 3 * self.LLM_COST
        assert row["cascade_est_cost_usd"] == pytest.approx(expected_cascade, abs=1e-9)
        assert row["llm_only_est_cost_usd"] == pytest.approx(n * self.LLM_COST)
        assert row["cost_ratio_cascade_vs_llm"] == pytest.approx(
            expected_cascade / (n * self.LLM_COST), abs=1e-4
        )


class TestScoreSemantics:
    """Normalization comparison: top-level certainty vs interpolated score."""

    def test_interpolated_normalization(self):
        assert _score_interpolated({"score": 5.4}) == pytest.approx(0.6)  # 5.4/9
        assert _score_interpolated({"score": 0}) == pytest.approx(0.0)
        assert _score_interpolated({"score": 9}) == pytest.approx(1.0)
        assert _score_interpolated({"score": 12}) == pytest.approx(1.0)  # clamped
        assert _score_interpolated({"nope": True}) is None
        assert _score_interpolated({}) is None

    def test_semantics_stats_both_normalizations(self):
        items = [
            {"label": 1, "score_probability": 0.6,
             "score_raw": {"type": "score", "score": 5.4}},
            {"label": 1, "score_probability": 0.3,
             "score_raw": {"type": "score", "score": 2.7}},
        ]
        semantics = score_semantics(items)
        top = semantics["top_level_certainty_probability"]
        interp = semantics["interpolated_score_normalized"]
        assert top["mean_conf"] == pytest.approx(0.45)
        assert top["accuracy_at_0.5"] == pytest.approx(0.5)
        assert interp["mean_conf"] == pytest.approx(0.45)
        assert interp["accuracy_at_0.5"] == pytest.approx(0.5)
        # ECE against all-positive labels = mean(1 - conf) here (one bin)
        assert top["ece_10bin"] == pytest.approx(0.55, abs=0.01)

    def test_semantics_skips_non_positive_labels(self):
        items = [
            {"label": 1, "score_probability": 0.6, "score_raw": {"score": 5.4}},
            {"label": 0, "score_probability": 0.9, "score_raw": {"score": 9.0}},
        ]
        semantics = score_semantics(items)
        assert semantics["top_level_certainty_probability"]["n"] == 1

    def test_semantics_none_without_score_data(self):
        assert score_semantics([{"label": 1, "score_probability": None}]) is None
        assert score_semantics([]) is None


class TestCascadeSimulation:
    """Benchmark cascade simulation + arm metrics on synthetic data."""

    def test_simulate_cascade_branches(self):
        jev = [0.9, 0.5, 0.65, 0.2]
        llm = [0.95, 0.6, None, 0.3]  # positionally aligned
        final, escalated, unresolved = simulate_cascade(jev, llm, tau=0.7)
        assert final == [0.9, 0.6, 0.65, 0.3]
        assert escalated == [False, True, True, True]
        assert unresolved == 1  # 0.65 escalated but no LLM measurement

    def test_arm_metrics_agreement_escalation_ece(self):
        final = [0.9, 0.6, 0.7, 0.3]
        escalated = [False, True, True, True]
        metrics = arm_metrics(final, escalated, est_cost_usd=0.001264)
        assert metrics["n_items"] == 4
        assert metrics["agreement_rate"] == pytest.approx(0.75)  # >= 0.5
        assert metrics["escalation_rate"] == pytest.approx(0.75)
        assert metrics["est_cost_usd"] == pytest.approx(0.001264)
        assert 0.0 <= metrics["ece_10bin"] <= 1.0

    def test_arm_metrics_empty(self):
        metrics = arm_metrics([], [], 0.0)
        assert metrics["agreement_rate"] is None
        assert metrics["escalation_rate"] is None
        assert metrics["ece_10bin"] is None


class TestBenchmarkRunMonkeypatched:
    """The benchmark main flow, fully monkeypatched (no live calls)."""

    ITEMS = [
        {"id": 101, "query": "q1", "reference_answer": "r1", "human_verdict": "pass"},
        {"id": 102, "query": "q2", "reference_answer": "r2", "human_verdict": "pass"},
        {"id": 103, "query": "q3", "reference_answer": "r3", "human_verdict": "pass"},
        {"id": 104, "query": "q4", "reference_answer": "r4", "human_verdict": "pass"},
    ]
    JEV = {101: 0.9, 102: 0.5, 103: 0.65, 104: 0.2}
    JEV_COSTS = {i: 1.6e-05 for i in JEV}
    LLM_CONFS = {101: 0.9, 102: 0.6, 103: 0.7, 104: 0.3}

    @pytest.fixture
    def benchmark_env(self, monkeypatch, tmp_path):
        import backend.tests.eval.decision_benchmark as bench

        monkeypatch.setattr(bench, "load_golden_items", lambda limit=None: self.ITEMS)
        monkeypatch.setattr(
            bench, "load_jev_confs", lambda items: (dict(self.JEV), dict(self.JEV_COSTS))
        )
        monkeypatch.setattr(bench, "_live_jev_fill", lambda missing: {})
        monkeypatch.setattr(bench, "_mlflow_log", lambda runs, tau: False)
        monkeypatch.setattr(
            bench, "BENCHMARK_REPORT_PATH", tmp_path / "benchmark_report.json"
        )

        generator = MagicMock()
        generator.decision_provider = None

        def _llm_conf(query, context, answer, system_prompt, *, cost_sink=None):
            item_id = 100 + int(query[1:])  # q1 → 101
            conf = self.LLM_CONFS[item_id]
            if cost_sink is not None:
                cost_sink.append(LLM_CALL_COST)
            return conf

        generator._llm_verbalized_confidence.side_effect = _llm_conf
        monkeypatch.setattr(bench, "RAGGenerator", MagicMock(return_value=generator))
        monkeypatch.setattr(
            "backend.src.rag.config.config", _mock_config(jev_escalation_threshold=0.7)
        )
        return bench, tmp_path / "benchmark_report.json"

    def test_run_all_arms_monkeypatched(self, benchmark_env):
        bench, report_path = benchmark_env
        report = bench.run(tau=0.7)

        arms = {a["arm"]: a for a in report["arms"]}
        assert set(arms) == {"llm-only", "jev-only", "cascade"}

        llm_arm = arms["llm-only"]
        # confs [0.9, 0.6, 0.7, 0.3]: 0.3 < 0.5 → agreement 3/4
        assert llm_arm["agreement_rate"] == pytest.approx(0.75)
        assert llm_arm["escalation_rate"] == 0.0
        assert llm_arm["est_cost_usd"] == pytest.approx(4 * LLM_CALL_COST)

        jev_arm = arms["jev-only"]
        # jev confs [0.9, 0.5, 0.65, 0.2]: 0.2 < 0.5 → agreement 3/4
        assert jev_arm["agreement_rate"] == pytest.approx(0.75)
        assert jev_arm["escalation_rate"] == 0.0
        assert jev_arm["est_cost_usd"] == pytest.approx(4 * 1.6e-05)

        cascade = arms["cascade"]
        # escalations: 102 (llm 0.6), 103 (llm 0.7), 104 (llm 0.3); 101 kept
        assert cascade["escalation_rate"] == pytest.approx(0.75)
        # final [0.9, 0.6, 0.7, 0.3] → 3/4 agree
        assert cascade["agreement_rate"] == pytest.approx(0.75)
        expected_cost = 4 * 1.6e-05 + 3 * LLM_CALL_COST
        assert cascade["est_cost_usd"] == pytest.approx(expected_cost)
        assert cascade["unresolved_escalations"] == 0

        assert report["tau"] == 0.7
        assert report["mlflow_logged"] is False
        assert report_path.exists()
        saved = json.loads(report_path.read_text())
        assert {a["arm"] for a in saved["arms"]} == {"llm-only", "jev-only", "cascade"}

    def test_run_reuses_stored_jev_without_live_calls(self, benchmark_env):
        bench, _ = benchmark_env
        live_fill = MagicMock()
        bench._live_jev_fill = live_fill  # would spend money if called

        bench.run(tau=0.7)

        live_fill.assert_not_called()
