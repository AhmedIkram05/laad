"""Regression tests for the phase-2 audit MEDIUM fixes (#8-#19)."""

from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
import requests

import backend.kafka.consumer as consumer_mod
import backend.src.rag.llm_client as llm_client
import backend.src.rag.retriever as retriever_mod
from backend.kafka.deduplicator import Deduplicator
from backend.src.rag.generator import RAGGenerator
from backend.src.rag.retriever import RetrievedChunk
from backend.src.rag.utils import QueryType


def _cfg(**overrides) -> SimpleNamespace:
    base = dict(
        is_configured=True,
        llm_api_key="key",
        llm_model="m",
        llm_base_url="http://x",
        rate_limit_per_min=0,
        temperature=0.1,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _chunk(cid="doc_1", distance=0.2, **kwargs) -> RetrievedChunk:
    return RetrievedChunk(
        text=kwargs.pop("text", "ERR_1234 ATM-GB-0001 cash dispenser jam"),
        chunk_id=cid,
        atm_id=kwargs.pop("atm_id", "ATM-GB-0001"),
        timestamp=kwargs.pop("timestamp", "2026-05-15T10:00:00Z"),
        distance=distance,
        confidence_score=kwargs.pop("confidence_score", 0.8),
        **kwargs,
    )


def _rate_limit_error() -> requests.exceptions.HTTPError:
    resp = MagicMock()
    resp.status_code = 429
    resp.headers = {}
    err = requests.exceptions.HTTPError("429 Too Many Requests")
    err.response = resp
    return err


# ---------------------------------------------------------------------------
# #8 — LLM retry budget & timeout backoff
# ---------------------------------------------------------------------------


class TestLLMRetryBudget:
    @staticmethod
    def _no_fallback_env():
        """Isolate from a real OPENROUTER/TYPESAFE key so only one provider exists."""
        return patch.dict(
            os.environ,
            {k: "" for k in ("OPENROUTER_API_KEY", "TYPESAFE_API_KEY")},
        )

    def test_rate_limit_budget_independent_of_attempt_count(self):
        """429s must not consume the attempt budget: MAX_RATE_LIMIT_RETRIES is
        reachable (6 requests per provider), not capped by MAX_RETRIES (3)."""
        with self._no_fallback_env(), patch.object(llm_client, "config", _cfg()):
            client = llm_client.LLMClient()
            calls = []

            def always_429(**kwargs):
                calls.append(1)
                raise _rate_limit_error()

            with patch.object(client, "_call_llm", side_effect=always_429):
                with patch.object(llm_client.time, "sleep"):
                    with pytest.raises(RuntimeError, match="All LLM providers failed"):
                        client.generate("q")
            assert len(calls) == llm_client.MAX_RATE_LIMIT_RETRIES + 1

    def test_timeout_gets_backoff_sleep_between_attempts(self):
        with self._no_fallback_env(), patch.object(llm_client, "config", _cfg()):
            client = llm_client.LLMClient()
            calls = []

            def always_timeout(**kwargs):
                calls.append(1)
                raise requests.exceptions.Timeout("timed out")

            with patch.object(client, "_call_llm", side_effect=always_timeout):
                with patch.object(llm_client.time, "sleep") as mock_sleep:
                    with pytest.raises(RuntimeError, match="All LLM providers failed"):
                        client.generate("q")
            assert len(calls) == llm_client.MAX_RETRIES + 1
            # Backoff sleeps between timeout attempts (previously zero).
            assert mock_sleep.call_count == llm_client.MAX_RETRIES

    def test_request_timeout_is_connect_read_tuple(self):
        connect, read = llm_client.REQUEST_TIMEOUT
        assert 0 < connect < read


# ---------------------------------------------------------------------------
# #9 — rate limiter waits instead of raising; request-scoped buckets
# ---------------------------------------------------------------------------


class TestRateLimiterWaitSemantics:
    def test_acquire_reserves_slot_when_under_limit(self):
        rl = llm_client.RateLimiter(max_requests=2, window_seconds=60)
        assert rl.acquire("req:1") is True
        assert rl.acquire("req:1") is True

    def test_acquire_returns_false_when_still_saturated_after_cap(self, monkeypatch):
        now = [1000.0]
        monkeypatch.setattr(llm_client.time, "time", lambda: now[0])
        monkeypatch.setattr(
            llm_client.time, "sleep", lambda s: now.__setitem__(0, now[0] + s)
        )
        rl = llm_client.RateLimiter(max_requests=1, window_seconds=60)
        assert rl.acquire("req", max_wait=5.0) is True
        # Window (60s) outlasts the wait cap (5s) → give up, do not raise here.
        assert rl.acquire("req", max_wait=5.0) is False

    def test_acquire_succeeds_after_window_slides(self, monkeypatch):
        now = [1000.0]
        monkeypatch.setattr(llm_client.time, "time", lambda: now[0])
        monkeypatch.setattr(
            llm_client.time, "sleep", lambda s: now.__setitem__(0, now[0] + s)
        )
        rl = llm_client.RateLimiter(max_requests=1, window_seconds=60)
        assert rl.acquire("req", max_wait=0.0) is True  # reserve the only slot
        # Cap wide enough that the limiter waits out the window instead of
        # failing — the pre-fix behavior raised immediately.
        assert rl.acquire("req", max_wait=70.0) is True
        assert now[0] >= 1055.0
        assert rl.acquire("req", max_wait=0.0) is False

    def test_acquire_zero_max_requests_never_crashes(self):
        rl = llm_client.RateLimiter(max_requests=0, window_seconds=60)
        assert rl.acquire("req", max_wait=0.0) is False


class TestGenerateRateLimitKey:
    def test_generate_uses_request_scoped_bucket(self):
        with patch.object(llm_client, "config", _cfg(rate_limit_per_min=20)):
            client = llm_client.LLMClient()
            with patch.object(llm_client, "_rate_limiter") as mock_rl:
                mock_rl.acquire.return_value = True
                with patch.object(
                    client, "_call_llm", return_value=MagicMock(text="ok")
                ):
                    client.generate("q", rate_limit_key="req:abc")
                assert mock_rl.acquire.call_args.args[0] == "req:abc"

    def test_generate_defaults_to_global_bucket(self):
        with patch.object(llm_client, "config", _cfg(rate_limit_per_min=20)):
            client = llm_client.LLMClient()
            with patch.object(llm_client, "_rate_limiter") as mock_rl:
                mock_rl.acquire.return_value = True
                with patch.object(
                    client, "_call_llm", return_value=MagicMock(text="ok")
                ):
                    client.generate("q")
                assert mock_rl.acquire.call_args.args[0] == "global"


# ---------------------------------------------------------------------------
# #10 — fallback uses the retrieved chunks
# ---------------------------------------------------------------------------


class TestFallbackUsesChunks:
    def test_generate_single_failure_uses_retrieved_chunks(self):
        gen = RAGGenerator()
        chunks = [_chunk(text="ERR_0042 fatal dispenser jam")]

        with patch.object(
            gen.llm_client, "generate", side_effect=RuntimeError("LLM down")
        ):
            resp = gen._generate_single(
                "cash jam",
                "ctx",
                "sys",
                QueryType.TROUBLESHOOTING,
                chunks=chunks,
            )

        assert resp.model == "fallback-template"
        # Rich chunk-based fallback, not the bare "not enough context" message.
        assert "Quick Troubleshooting Steps" in resp.text

    def test_generate_single_without_chunks_keeps_plain_fallback(self):
        gen = RAGGenerator()
        with patch.object(
            gen.llm_client, "generate", side_effect=RuntimeError("LLM down")
        ):
            resp = gen._generate_single(
                "cash jam", "ctx", "sys", QueryType.TROUBLESHOOTING, chunks=None
            )
        assert "I don't have enough context" in resp.text


# ---------------------------------------------------------------------------
# #19 — cross_encoder_used reports the real rerank flag
# ---------------------------------------------------------------------------


class TestCrossEncoderFlagPropagation:
    def test_generator_reports_flag_from_chunks(self):
        gen = RAGGenerator()
        kwargs = dict(
            enable_reflexion=False,
            enable_citation_grounding=False,
            enable_self_consistency=False,
        )
        with patch.object(
            gen.llm_client,
            "generate",
            return_value=llm_client.LLMResponse(
                text="answer", raw_response={}, model="m", finish_reason="STOP"
            ),
        ):
            # No rerank ran → False (was: inferred True from confidence > 0).
            resp = gen.generate("q", [_chunk()], **kwargs)
            assert resp.cross_encoder_used is False

            # Retriever marked the chunk as reranked → True.
            resp = gen.generate("q", [_chunk(cross_encoder_used=True)], **kwargs)
            assert resp.cross_encoder_used is True


# ---------------------------------------------------------------------------
# #18 — hybrid fusion keeps true cosine distance
# ---------------------------------------------------------------------------


class TestHybridKeepsTrueDistance:
    @staticmethod
    def _retriever() -> retriever_mod.RAGRetriever:
        r = retriever_mod.RAGRetriever.__new__(retriever_mod.RAGRetriever)
        r._sparse_cache = {}
        r._token_cache = {}
        r._cross_encoder = None
        return r

    def test_dense_chunk_keeps_true_distance(self, monkeypatch):
        r = self._retriever()
        monkeypatch.setattr(
            r,
            "_sparse_pool",
            lambda wf: (
                ["s1"],
                ["sparse text cash fault"],
                [{}],
                {"sparse": 1, "text": 1, "cash": 1, "fault": 1},
                4.0,
            ),
        )
        dense = [
            _chunk(
                "d1",
                distance=0.42,
                text="atm cash dispenser fault",
                confidence_score=0.58,
            )
        ]

        out = r._fuse_hybrid("cash fault", dense, None, 6)

        dense_out = next(c for c in out if c.chunk_id == "d1")
        # True vector distance is preserved, not overwritten by RRF rank.
        assert dense_out.distance == 0.42
        assert dense_out.confidence_score == 0.58
        assert dense_out.rrf_score is not None

        sparse_out = next(c for c in out if c.chunk_id == "s1")
        assert 0.0 <= sparse_out.distance <= 1.0
        assert sparse_out.rrf_score is not None


# ---------------------------------------------------------------------------
# #11 — handlers buffer rows; consumer flushes once per poll batch
# ---------------------------------------------------------------------------


class TestHandlerRowBuffering:
    def test_event_row_buffer_skips_db_and_appends(self):
        import backend.kafka.handlers.event_handler as eh

        msg = {
            "message_id": "m",
            "timestamp": "2026-05-12T10:00:00Z",
            "source": "ATM_APP",
            "severity": "INFO",
            "atm_id": "ATM-GB-0001",
        }
        with patch.object(eh, "get_cursor") as mock_gc:
            buf: list[tuple] = []
            assert eh.handle_event(msg, MagicMock(), row_buffer=buf) is True
            assert mock_gc.call_count == 0
            assert len(buf) == 1
            assert buf[0][1] == "ATM_APP"

    def test_metric_row_buffer_skips_db_and_appends(self):
        import backend.kafka.handlers.metric_handler as mh

        msg = {
            "message_id": "m",
            "timestamp": "2026-05-12T10:00:00Z",
            "source": "PROMETHEUS",
            "entity_id": "ATM-GB-0001",
            "metric_name": "cpu",
            "metric_value": 0.5,
        }
        with patch.object(mh, "get_cursor") as mock_gc:
            buf: list[tuple] = []
            assert mh.handle_metric(msg, row_buffer=buf) is True
            assert mock_gc.call_count == 0
            assert len(buf) == 1
            assert buf[0][4] == 0.5

    def test_batch_insert_sql_is_execute_values_template(self):
        import backend.kafka.handlers.event_handler as eh
        import backend.kafka.handlers.metric_handler as mh

        for sql in (eh.EVENT_BATCH_INSERT_SQL, mh.METRIC_BATCH_INSERT_SQL):
            assert "VALUES %s" in sql

    def test_flush_rows_uses_write_batch_once(self):
        rows = [(1,), (2,)]
        with (
            patch.object(consumer_mod, "write_batch") as wb,
            patch.object(consumer_mod, "get_conn", return_value="conn"),
        ):
            assert consumer_mod.flush_rows(rows, "INSERT INTO t VALUES %s", "t") is True
            wb.assert_called_once_with("conn", "INSERT INTO t VALUES %s", rows)

    def test_flush_rows_failure_reports_false(self):
        with (
            patch.object(
                consumer_mod, "write_batch", side_effect=RuntimeError("db down")
            ),
            patch.object(consumer_mod, "get_conn", return_value="conn"),
        ):
            assert (
                consumer_mod.flush_rows([(1,)], "INSERT INTO t VALUES %s", "t") is False
            )

    def test_flush_rows_empty_is_noop(self):
        with patch.object(consumer_mod, "write_batch") as wb:
            assert consumer_mod.flush_rows([], "INSERT INTO t VALUES %s", "t") is True
            wb.assert_not_called()


# ---------------------------------------------------------------------------
# #12 — SageMaker client gets explicit timeouts
# ---------------------------------------------------------------------------


class TestSageMakerTimeout:
    def test_invoke_client_gets_explicit_timeouts(self):
        import backend.src.anomaly_detection.ml.ml_detector as ml

        fake_boto3 = MagicMock()
        fake_cfg_mod = MagicMock()
        captured: dict = {}

        def fake_config(**kwargs):
            captured.update(kwargs)
            return SimpleNamespace(**kwargs)

        fake_cfg_mod.Config = fake_config
        fake_response = {"Body": MagicMock()}
        fake_response["Body"].read.return_value.decode.return_value = "1.0"
        fake_boto3.client.return_value.invoke_endpoint.return_value = fake_response

        env = {"SAGEMAKER_ENDPOINT_NAME": "test-endpoint"}
        modules = {
            "boto3": fake_boto3,
            "botocore": SimpleNamespace(config=fake_cfg_mod),
            "botocore.config": fake_cfg_mod,
        }
        detector = SimpleNamespace()
        with patch.dict(os.environ, env), patch.dict("sys.modules", modules):
            result = ml.MLAnomalyDetector._sagemaker_predict(detector, np.zeros((1, 2)))

        assert result == {"raw_prediction": "1.0"}
        assert captured["connect_timeout"] == ml.SAGEMAKER_CONNECT_TIMEOUT_S
        assert captured["read_timeout"] == ml.SAGEMAKER_READ_TIMEOUT_S


# ---------------------------------------------------------------------------
# #13 — per-message dedup keys, single round-trip, periodic re-probe
# ---------------------------------------------------------------------------


class TestDedupPerMessageKeys:
    def test_check_and_mark_single_roundtrip_per_message_key(self):
        client = MagicMock()
        client.ping.return_value = True
        client.set.return_value = True  # key created → not a duplicate
        with patch("backend.kafka.deduplicator.get_redis_client", return_value=client):
            d = Deduplicator()
            assert d.check_and_mark("m1") is False
            assert client.set.call_count == 1
            args, kwargs = client.set.call_args
            assert args[0] == "kafka:dedup:id:m1"
            assert kwargs["nx"] is True
            assert kwargs["ex"] == 3600

    def test_check_and_mark_detects_duplicate(self):
        client = MagicMock()
        client.ping.return_value = True
        client.set.return_value = None  # NX failed → key existed
        with patch("backend.kafka.deduplicator.get_redis_client", return_value=client):
            d = Deduplicator()
            assert d.check_and_mark("m1") is True

    def test_check_and_mark_falls_back_to_memory_when_redis_down(self):
        with patch.object(Deduplicator, "_is_redis_available", return_value=False):
            d = Deduplicator(max_size=10)
            assert d.check_and_mark("m1") is False
            assert d.check_and_mark("m1") is True

    def test_redis_unavailability_is_reprobed_after_window(self):
        client = MagicMock()
        client.ping.side_effect = RuntimeError("redis down")
        with patch("backend.kafka.deduplicator.get_redis_client", return_value=client):
            d = Deduplicator()
            assert d._is_redis_available() is False
            assert d._probe_after is not None
            # Simulate the re-probe window elapsing.
            d._probe_after = 0.0
            assert d._is_redis_available() is False
            assert client.ping.call_count == 2

    def test_pinned_unavailable_state_does_not_probe(self):
        client = MagicMock()
        with patch("backend.kafka.deduplicator.get_redis_client", return_value=client):
            d = Deduplicator()
            d._use_redis = False  # explicit pin (no probe window scheduled)
            assert d._is_redis_available() is False
            client.ping.assert_not_called()


# ---------------------------------------------------------------------------
# #14 — detection lock ownership (token-checked release) + TTL floor
# ---------------------------------------------------------------------------


class TestDetectionLockOwnership:
    def test_acquire_returns_token_release_uses_compare_delete(self):
        client = MagicMock()
        client.set.return_value = True
        with patch.object(consumer_mod, "get_redis_client", return_value=client):
            should_run, token = consumer_mod._acquire_detection_lock()
            assert should_run is True
            assert token
            consumer_mod._release_detection_lock(token)
            client.eval.assert_called_once()
            lua, numkeys, key, tok = client.eval.call_args.args
            assert tok == token
            assert key == consumer_mod.LOCK_KEY

    def test_acquire_denied_when_lock_held(self):
        client = MagicMock()
        client.set.return_value = False
        with patch.object(consumer_mod, "get_redis_client", return_value=client):
            should_run, token = consumer_mod._acquire_detection_lock()
            assert should_run is False
            assert token is None

    def test_release_without_token_is_noop(self):
        client = MagicMock()
        with patch.object(consumer_mod, "get_redis_client", return_value=client):
            consumer_mod._release_detection_lock(None)
            client.eval.assert_not_called()
            client.delete.assert_not_called()

    def test_lock_ttl_floored_at_interval(self):
        assert consumer_mod.LOCK_TIMEOUT_S >= consumer_mod.ANOMALY_INTERVAL_S
        assert consumer_mod.LOCK_TIMEOUT_S > 0


# ---------------------------------------------------------------------------
# #15 — server-side default limit for the anomalies list
# ---------------------------------------------------------------------------


class TestAnomaliesDefaultLimit:
    def test_list_endpoint_default_limit_is_bounded(self):
        import inspect

        from backend.src.anomalies.anomalies_router import listAnomalies

        default = inspect.signature(listAnomalies).parameters["limit"].default
        assert getattr(default, "default", None) == 200


# ---------------------------------------------------------------------------
# #13 companion — consumer module docstring reflects the Redis-backed dedup
# ---------------------------------------------------------------------------


class TestConsumerDocstring:
    def test_module_docstring_no_longer_claims_in_memory_only(self):
        import backend.kafka.consumer as c

        assert "in-memory LRU set" not in c.__doc__
        assert "Redis" in c.__doc__
