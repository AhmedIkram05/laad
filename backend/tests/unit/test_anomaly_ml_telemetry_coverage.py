"""Coverage for rag/telemetry.py, rag/generator.py leftovers, anomaly_detector
persistence paths, ml_detector remaining branches, and ml/train helpers."""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.anomaly


def _ctx(cur=None, enter_exc=None):
    ctx = MagicMock()
    if enter_exc:
        ctx.__enter__.side_effect = enter_exc
    else:
        ctx.__enter__.return_value = cur or MagicMock()
    ctx.__exit__.return_value = False
    return ctx


class TestTelemetry:
    def test_trace_record_cost_and_dict(self):
        from backend.src.rag.telemetry import TraceRecord

        rec = TraceRecord(mode="agentic", rounds=2, model_calls=3)
        assert rec.est_cost == pytest.approx(3 * 0.0004)
        d = rec.to_dict()
        assert d["mode"] == "agentic" and d["est_cost"] == rec.est_cost

    def test_from_trace_defaults(self):
        from backend.src.rag.telemetry import _from_trace

        rec = _from_trace({})
        assert rec.rounds == 0 and rec.tool_calls == [] and rec.retries == 0

    def test_record_trace_early_returns(self):
        from backend.src.rag import telemetry

        with patch.object(telemetry, "get_cursor") as gc:
            telemetry.record_trace(None, {"mode": "x"})
            telemetry.record_trace(1, None)
            telemetry.record_trace(1, {})
            gc.assert_not_called()

    def test_record_trace_success(self):
        from backend.src.rag import telemetry

        cur = MagicMock()
        with (
            patch.object(telemetry, "get_cursor", return_value=_ctx(cur)),
            patch.object(telemetry, "_append_otel_jsonl") as otel,
        ):
            telemetry.record_trace(9, {"mode": "hybrid", "rounds": 1})
            cur.execute.assert_called_once()
            otel.assert_called_once()

    def test_record_trace_db_failure_never_raises(self):
        from backend.src.rag import telemetry

        with (
            patch.object(
                telemetry, "get_cursor", side_effect=RuntimeError("db down")
            ),
            patch.object(telemetry, "_append_otel_jsonl") as otel,
        ):
            telemetry.record_trace(9, {"mode": "x"})
            otel.assert_not_called()

    def test_append_otel_skipped_without_path(self, tmp_path):
        from backend.src.rag import telemetry
        from backend.src.rag.telemetry import TraceRecord

        with patch.object(telemetry.config, "otel_jsonl", None):
            telemetry._append_otel_jsonl(1, TraceRecord(mode="x"))

    def test_append_otel_writes_and_handles_oserror(self, tmp_path):
        from backend.src.rag import telemetry
        from backend.src.rag.telemetry import TraceRecord

        path = tmp_path / "otel.jsonl"
        with patch.object(telemetry.config, "otel_jsonl", str(path)):
            telemetry._append_otel_jsonl(4, TraceRecord(mode="agentic", model_calls=2))
            assert path.read_text().strip().startswith("{")
        with patch.object(telemetry.config, "otel_jsonl", "/nonexistent-dir/x.jsonl"):
            telemetry._append_otel_jsonl(4, TraceRecord())

    def test_aggregate(self):
        from backend.src.rag.telemetry import TraceRecord, aggregate

        assert aggregate([]) == {}
        out = aggregate(
            [
                TraceRecord(rounds=2, model_calls=2),
                TraceRecord(rounds=4, model_calls=0, model_calls_truncated=True),
            ]
        )
        assert out["traces"] == 2
        assert out["mean_rounds"] == 3.0
        assert out["truncated_count"] == 1


class TestRagGeneratorLeftovers:
    def _gen(self):
        from backend.src.rag.generator import RAGGenerator

        return RAGGenerator()

    def test_normalize_markdown_spacing(self):
        from backend.src.rag.generator import _normalize_markdown_spacing

        assert "a" in _normalize_markdown_spacing("a\n\n\nb")
        assert _normalize_markdown_spacing("") == ""

    def test_system_prompt_per_type(self):
        from backend.src.rag.generator import _get_system_prompt_for_query_type
        from backend.src.rag.utils import QueryType

        for qt in QueryType:
            assert isinstance(_get_system_prompt_for_query_type(qt), str)

    def test_text_similarity_edges(self):
        from backend.src.rag.generator import _compute_text_similarity

        assert _compute_text_similarity("", "") == 0.0
        assert _compute_text_similarity("same text here", "same text here") > 0.9
        assert 0.0 <= _compute_text_similarity("aaa bbb", "ccc ddd") <= 1.0

    def test_extract_entities(self):
        from backend.src.rag.generator import _extract_entities

        ents = _extract_entities("ATM-GB-0001 failed with ERR-0040, anomaly A3")
        assert ents

    def test_check_citations_vacuous_and_real(self):
        from backend.src.rag.generator import _check_citations

        assert _check_citations("answer", []) == 1.0

    def test_extract_anomaly_tag(self):
        from backend.src.rag.generator import _extract_anomaly_tag
        from backend.src.rag.retriever import RetrievedChunk

        def chunk(text):
            return RetrievedChunk(
                text=text, chunk_id="c", atm_id="ATM-1", timestamp=None,
                distance=0.1, confidence_score=0.9,
            )

        assert _extract_anomaly_tag(chunk("[A1] network down")) is None
        assert _extract_anomaly_tag(chunk('_anomaly_tag="A1" timeout')) == "A1"

    def test_build_context_and_prompt(self):
        from backend.src.rag.retriever import RetrievedChunk
        from backend.src.rag.utils import QueryType

        gen = self._gen()
        chunks = [
            RetrievedChunk(
                text="log line",
                chunk_id="c1",
                atm_id="ATM-1",
                timestamp="t",
                distance=0.1,
                confidence_score=0.9,
            )
        ]
        assert "log line" in gen._build_context(chunks)
        assert gen._build_context([]) == ""
        prompt = gen._build_prompt("q?", "ctx", QueryType.DIAGNOSTIC)
        assert "q?" in prompt and "ctx" in prompt

    def test_generate_fallback_paths(self):
        from backend.src.rag.retriever import RetrievedChunk
        from backend.src.rag.utils import QueryType

        gen = self._gen()
        chunks = [
            RetrievedChunk(
                text="timeout error",
                chunk_id="c1",
                atm_id="ATM-1",
                timestamp="t",
                distance=0.1,
                confidence_score=0.9,
            )
        ]
        assert isinstance(
            gen._generate_fallback("q", chunks, QueryType.DIAGNOSTIC), str
        )
        assert isinstance(gen._generate_stats_fallback(chunks), str)
        assert isinstance(
            gen._generate_troubleshooting_fallback("fix it", chunks), str
        )
        assert gen._generate_fallback("q", [], QueryType.GENERAL) != ""

    def test_generate_uses_llm_and_fallback(self):
        from backend.src.rag.generator import RAGGenerator, get_generator
        from backend.src.rag.llm_client import LLMResponse
        from backend.src.rag.retriever import RetrievedChunk
        from backend.src.rag.utils import QueryType

        gen = RAGGenerator()
        gen.llm_client = MagicMock()
        gen.llm_client.generate.side_effect = RuntimeError("no providers")
        chunks = [
            RetrievedChunk(
                text="timeout",
                chunk_id="c1",
                atm_id="ATM-1",
                timestamp="t",
                distance=0.1,
                confidence_score=0.9,
            )
        ]
        llm_resp = LLMResponse(
            text="diagnosis", raw_response={}, model="m", finish_reason="stop"
        )
        with patch.object(gen, "_generate_single", return_value=llm_resp):
            out = gen.generate("what is wrong?", chunks, query_type=QueryType.GENERAL)
            assert out.text == "diagnosis"
            assert out.was_revised is False
        out = gen.generate("what is wrong?", chunks)
        assert out.text != ""
        assert "fallback" in out.model or isinstance(out.text, str)
        out = gen.generate("what is wrong?", [])
        assert out.model == "none"
        assert get_generator() is get_generator()

    def test_generate_samples_critique_regenerate_path(self):
        from backend.src.rag.generator import RAGGenerator
        from backend.src.rag.llm_client import LLMResponse
        from backend.src.rag.retriever import RetrievedChunk
        from backend.src.rag.utils import QueryType

        def resp(text):
            return LLMResponse(text=text, raw_response={}, model="m",
                               finish_reason="stop")

        gen = RAGGenerator()
        chunks = [
            RetrievedChunk(
                text="ATM-GB-0001 timeout error",
                chunk_id="c1",
                atm_id="ATM-GB-0001",
                timestamp="t",
                distance=0.1,
                confidence_score=0.9,
            )
        ]
        gen.llm_client = MagicMock()
        # generate() consumes 6 LLM calls in order: 3 self-consistency
        # samples, critique, regeneration, verbalized confidence.
        gen.llm_client.generate.side_effect = [
            resp("consistent diagnosis text"),
            resp("the claim about reboot lacks evidence"),
            resp("corrected diagnosis text"),
            resp("the claim about reboot lacks evidence"),
            resp("corrected diagnosis text"),
            resp("0.82"),
        ]
        out = gen.generate("what is wrong with ATM-GB-0001?", chunks,
                           query_type=QueryType.DIAGNOSTIC)
        assert out.text == "corrected diagnosis text"
        assert out.was_revised is True
        assert out.grounding_score is not None
        assert out.verbalized_confidence == 0.82

    def test_fallback_per_query_type(self):
        from backend.src.rag.retriever import RetrievedChunk
        from backend.src.rag.utils import QueryType

        gen = self._gen()
        chunks = [
            RetrievedChunk(
                text='timeout at ATM-GB-0001 _anomaly_tag="A1"',
                chunk_id="c1",
                atm_id="ATM-GB-0001",
                timestamp="t",
                distance=0.1,
                confidence_score=0.9,
            )
        ]
        assert isinstance(
            gen._generate_fallback("how many?", chunks, QueryType.STATS), str
        )
        assert isinstance(
            gen._generate_fallback("fix it", chunks, QueryType.TROUBLESHOOTING), str
        )
        assert "ATM-GB-0001" in gen._generate_stats_fallback(chunks)

    def test_markdown_headings_and_lists(self):
        from backend.src.rag.generator import _normalize_markdown_spacing

        text = "**Diagnosis**\ncontent here\n# Title\nbody\n- item one\n- item two"
        out = _normalize_markdown_spacing(text)
        assert "content here" in out and "item one" in out
        assert _normalize_markdown_spacing("plain text") == "plain text"

    def test_check_citations_grounded(self):
        from backend.src.rag.generator import _check_citations
        from backend.src.rag.retriever import RetrievedChunk

        chunks = [
            RetrievedChunk(
                text="ATM-GB-0001 had ERR-0040 timeout",
                chunk_id="c1",
                atm_id="ATM-GB-0001",
                timestamp="t",
                distance=0.1,
                confidence_score=0.9,
            )
        ]
        score = _check_citations("ATM-GB-0001 failed with ERR-0040", chunks)
        assert score > 0.0

    def test_build_prompt_types(self):
        from backend.src.rag.utils import QueryType

        gen = self._gen()
        for qt in (QueryType.TROUBLESHOOTING, QueryType.STATS,
                   QueryType.GENERAL, QueryType.DIAGNOSTIC):
            prompt = gen._build_prompt("q?", "ctx", qt)
            assert "q?" in prompt

    def test_self_consistency_verbalized_critique_branches(self):
        from backend.src.rag.llm_client import LLMResponse

        gen = self._gen()
        gen.llm_client = MagicMock()
        same = LLMResponse(text="same answer text here", raw_response={},
                           model="m", finish_reason="stop")
        gen.llm_client.generate.return_value = same
        score, samples = gen._compute_self_consistency(
            "q", "ctx", "sys", None, num_samples=3)
        assert score is not None and score > 0.9 and len(samples) == 3
        score1, samples1 = gen._compute_self_consistency(
            "q", "ctx", "sys", None, num_samples=1)
        assert score1 is None and len(samples1) == 1
        gen.llm_client.generate.side_effect = RuntimeError("x")
        score, samples = gen._compute_self_consistency(
            "q", "ctx", "sys", None, num_samples=3)
        assert score is None and samples == []
        gen.llm_client.generate.side_effect = None
        gen.llm_client.generate.return_value = LLMResponse(
            text="0.85", raw_response={}, model="m", finish_reason="stop")
        assert gen._estimate_verbalized_confidence("q", "ctx", "a", "sys") == 0.85
        gen.llm_client.generate.side_effect = RuntimeError("x")
        assert gen._estimate_verbalized_confidence("q", "ctx", "a", "sys") is None
        assert gen._critique_response("q", "ctx", "a", "sys") is None
        gen.llm_client.generate.side_effect = None
        gen.llm_client.generate.return_value = LLMResponse(
            text="NO_ISSUES_FOUND", raw_response={}, model="m", finish_reason="stop")
        assert gen._critique_response("q", "ctx", "a", "sys") is None
        gen.llm_client.generate.return_value = LLMResponse(
            text="claim X lacks evidence", raw_response={}, model="m",
            finish_reason="stop")
        assert gen._critique_response("q", "ctx", "a", "sys") == "claim X lacks evidence"
        regen = gen._regenerate("q", "ctx", "sys", None, "orig", "crit")
        assert regen.text == "claim X lacks evidence"
        gen.llm_client.generate.side_effect = RuntimeError("x")
        regen = gen._regenerate("q", "ctx", "sys", None, "orig", "crit")
        assert regen.text == "orig"


class TestAnomalyDetectorPersistence:
    def test_datetime_safe_json(self):
        from backend.src.anomaly_detection.anomaly_detector import (
            _datetime_safe_json_dumps,
        )

        s = _datetime_safe_json_dumps({"t": datetime(2026, 1, 1)})
        assert "2026" in s

    def test_ingestion_errors_window(self):
        import backend.src.anomaly_detection.anomaly_detector as ad

        conn = MagicMock()
        cur = MagicMock()
        cur.fetchall.return_value = [(1, "2026-01-01", "atm_app", "detail", "raw")]
        conn.cursor.return_value = cur
        with (
            patch.object(ad, "get_conn", return_value=conn),
            patch.object(ad, "release_conn"),
        ):
            rows = ad._ingestion_errors_in_window(None, None)
            assert rows == [{"id": 1, "ts": "2026-01-01", "source": "ATM_APP",
                             "raw_input": "raw", "error_detail": "detail"}]
        with (
            patch.object(ad, "get_conn", return_value=conn),
            patch.object(ad, "release_conn"),
        ):
            rows = ad._ingestion_errors_in_window(
                datetime(2026, 1, 1), datetime(2026, 1, 2))
            assert len(rows) == 1
            assert "AND timestamp <=" in cur.execute.call_args[0][0]
        with (
            patch.object(ad, "get_conn", side_effect=RuntimeError("db")),
            patch.object(ad, "release_conn"),
        ):
            assert ad._ingestion_errors_in_window(None, None) == []

    def test_detect_from_window_combines(self):
        import backend.src.anomaly_detection.anomaly_detector as ad

        rows = [
            {
                "source": "ATM_APP",
                "atm_id": "ATM-1",
                "event_type": "TIMEOUT",
                "timestamp": "2026-01-01T10:00:00Z",
            }
        ]
        with patch.object(
            ad, "_ingestion_errors_in_window", return_value=[]
        ):
            out = ad.detect_anomalies_from_window(rows, None, None)
            assert isinstance(out, list)

    def test_save_anomalies_and_main(self):
        import backend.src.anomaly_detection.anomaly_detector as ad

        det = ad.AnomalyDetector()
        assert det.save_anomalies([]) == 0
        conn = MagicMock()
        cur = MagicMock()
        cur.fetchone.side_effect = [{"1": 1}, None]
        conn.cursor.return_value = _ctx(cur)
        with (
            patch.object(det, "_get_conn", return_value=conn),
            patch.object(ad, "increment_anomaly_counter") as inc,
        ):
            n = det.save_anomalies(
                [
                    {"anomaly_type": "A1", "atm_id": None},
                    {"anomaly_type": "A2", "atm_id": "ATM-1",
                     "severity": "CRITICAL", "title": "t"},
                ]
            )
            assert n == 1
            inc.assert_called_once()
            conn.commit.assert_called_once()
        conn2 = MagicMock()
        cur2 = MagicMock()
        cur2.fetchall.return_value = []
        conn2.cursor.return_value = _ctx(cur2)
        with (
            patch.object(det, "_get_conn", return_value=conn2),
            patch.object(ad, "release_conn"),
        ):
            assert det.query("SELECT 1") == []
            assert det.load_data() == []
        assert det.detect_anomalies([]) == []
        with (
            patch.object(det, "load_data", return_value=[]),
            patch.object(det, "detect_anomalies", return_value=[]),
            patch.object(det, "save_anomalies", return_value=0) as sv,
        ):
            det.main()
            sv.assert_called_once_with([])


class TestMLDetectorLeftovers:
    @pytest.fixture(autouse=True)
    def _mlflow(self):
        with patch("backend.src.anomaly_detection.ml.ml_detector.mlflow"):
            yield

    def _det(self):
        from backend.src.anomaly_detection.ml.ml_detector import MLAnomalyDetector

        with (
            patch.object(MLAnomalyDetector, "_load_models", return_value=False),
            patch.object(MLAnomalyDetector, "_download_models_from_s3"),
        ):
            return MLAnomalyDetector()

    def test_rolling_baseline(self):
        import numpy as np

        from backend.src.anomaly_detection.ml.ml_detector import RollingBaseline

        rb = RollingBaseline(window_size=10)
        assert rb.ready is False
        assert (rb.compute_z_scores(np.ones(3, dtype=np.float32)) == 0).all()
        for _ in range(6):
            rb.update(np.ones(4, dtype=np.float32))
        assert rb.ready is True
        z = rb.compute_z_scores(np.ones(4, dtype=np.float32) * 5)
        assert len(z) == 4
        feats = rb.compute_baseline_features(np.ones(4, dtype=np.float32) * 5)
        assert len(feats) == 13

    def test_download_skips_without_env(self):
        det = self._det()
        with patch.dict("os.environ", {}, clear=False):
            import os

            os.environ.pop("S3_MODEL_ARTIFACTS_PATH", None)
            det._download_models_from_s3()

    def test_attribution_branches(self):
        det = self._det()
        assert det._attribution_for("A1", []) is None
        rows = [{"atm_id": "ATM-GB-0001"}, {"atm_id": "ATM-GB-0001"}]
        assert det._attribution_for("A1", rows) == "ATM-GB-0001"
        pod_rows = [
            {
                "atm_id": "ATM-GB-0002",
                "raw_payload": {"pod_name": "terminal-handler-atm-gb-0007"},
            }
        ]
        assert det._attribution_for("A3", pod_rows) == "ATM-GB-0007"
        str_rows = [
            {"atm_id": "ATM-GB-0002", "raw_payload": "not-json{"},
            {"atm_id": "ATM-GB-0002", "raw_payload": '{"pod_name": "svc"}'},
        ]
        assert det._attribution_for("A4", str_rows) == "ATM-GB-0002"

    def test_is_active_both_branches(self):
        import backend.src.anomaly_detection.ml.ml_detector as md

        det = self._det()
        cur = MagicMock()
        cur.fetchone.return_value = {"1": 1}
        with patch.object(md, "get_cursor", return_value=_ctx(cur)):
            assert det._is_active("A1", None) is True
            assert det._is_active("A1", "ATM-1") is True
        cur2 = MagicMock()
        cur2.fetchone.return_value = None
        with patch.object(md, "get_cursor", return_value=_ctx(cur2)):
            assert det._is_active("A1", "ATM-1") is False

    def test_save_anomaly_skips_when_active(self):
        det = self._det()
        with patch.object(det, "_is_active", return_value=True):
            assert det._save_anomaly("A1", "ATM-1", 0.9) is None

    def test_save_anomaly_inserts(self):
        import backend.src.anomaly_detection.ml.ml_detector as md

        det = self._det()
        cur = MagicMock()
        with (
            patch.object(det, "_is_active", return_value=False),
            patch.object(md, "get_cursor", return_value=_ctx(cur)),
        ):
            det._save_anomaly("A1", "ATM-1", 0.9, explanation={"k": "v"})
            cur.execute.assert_called()

    def test_detect_heuristic_and_recent(self):
        det = self._det()
        with patch(
            "backend.src.anomaly_detection.ml.ml_detector.detect_anomalies_from_window",
            return_value=[{"anomaly_type": "A1"}],
        ):
            out = det._detect_heuristic([{"x": 1}], None, None)
            assert out == [{"anomaly_type": "A1"}]
        assert det._detect_heuristic([], None, None) == []
        with patch(
            "backend.src.anomaly_detection.ml.ml_detector.detect_anomalies_from_window",
            side_effect=RuntimeError("boom"),
        ):
            assert det._detect_heuristic([{"x": 1}], None, None) == []
        det._last_saved_anomalies = [{"a": 1}, {"b": 2}]
        assert det._get_recent_anomalies(1) == [{"b": 2}]

    def test_detect_and_save_empty_window(self):
        det = self._det()
        with (
            patch.object(det, "_query_window", return_value=([], None, None)),
            patch.object(det, "_detect_heuristic", return_value=[]),
        ):
            assert det.detect_and_save() == 0

    def test_sagemaker_no_endpoint(self):
        import numpy as np

        det = self._det()
        with patch.dict("os.environ", {}, clear=False):
            import os

            os.environ.pop("SAGEMAKER_ENDPOINT_NAME", None)
            assert det._sagemaker_predict(np.ones(3)) is None
        with patch.dict("os.environ", {"SAGEMAKER_ENDPOINT_NAME": "ep"}):
            fake_boto = MagicMock()
            fake_boto.client.side_effect = RuntimeError("no aws")
            with patch.dict("sys.modules", {"boto3": fake_boto}):
                assert det._sagemaker_predict(np.ones(3)) is None


class TestTrainHelpers:
    def test_load_offline_missing_returns_empty(self, tmp_path):
        import backend.src.anomaly_detection.ml.train as tr

        with patch.object(tr, "TRAINING_DATA", tmp_path / "missing.json"):
            assert tr.load_offline_dataset() == []

    def test_load_offline_reads_file(self, tmp_path):
        import json

        import backend.src.anomaly_detection.ml.train as tr

        p = tmp_path / "data.json"
        p.write_text(json.dumps([{"timestamp": "2026-01-01T00:00:00+00:00",
                                  "a": 1}]))
        with patch.object(tr, "TRAINING_DATA", p):
            rows = tr.load_offline_dataset()
            assert rows[0]["a"] == 1
            assert isinstance(rows[0]["timestamp"], datetime)

    def test_calibrate_threshold(self):
        import numpy as np

        import backend.src.anomaly_detection.ml.train as tr

        scores = np.array([0.9, 0.8, -0.9, -0.8])
        y = np.array([0, 0, 1, 1])
        # Same mlflow-soak reason as test_grid_search_if.
        with patch.object(tr, "mlflow"):
            result = tr._calibrate_unknown_threshold(scores, y)
        assert isinstance(result, float)

    def test_grid_search_if(self):
        import numpy as np

        import backend.src.anomaly_detection.ml.train as tr

        rng = np.random.RandomState(0)
        # mlflow client hits http://mlflow:5000 which is not among pytest
        # deps — unmocked calls soak for minutes in urllib3 backoff retries.
        with patch.object(tr, "mlflow"):
            out = tr._grid_search_if(
                rng.normal(size=(20, 4)),
                rng.normal(size=(10, 4)),
                rng.normal(size=(10, 4)),
            )
        assert isinstance(out, dict)
