"""Coverage for analysis.py, analysis_router.py, analytics_router.py."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import backend.src.analysis.analysis as analysis
from backend.src.analysis import analysis_router
from backend.src.analytics import analytics_router

pytestmark = pytest.mark.analytics


def _analysis_client():
    app = FastAPI()
    app.include_router(analysis_router.router)
    return TestClient(app, raise_server_exceptions=False)


def _analytics_client():
    app = FastAPI()
    app.include_router(analytics_router.router)
    return TestClient(app, raise_server_exceptions=False)


def _cursor(rows=None, one=None, rows_seq=None, one_seq=None):
    cur = MagicMock()
    cur.fetchall.side_effect = rows_seq if rows_seq is not None else [rows or []]
    cur.fetchone.side_effect = one_seq if one_seq is not None else [one or {}]
    ctx = MagicMock()
    ctx.__enter__.return_value = cur
    ctx.__exit__.return_value = False
    conn = MagicMock()
    conn.cursor.return_value = ctx
    return conn, cur


def _failing_conn():
    conn = MagicMock()
    ctx = MagicMock()
    ctx.__enter__.side_effect = RuntimeError("db down")
    conn.cursor.return_value = ctx
    return conn


class TestAnalysisHelpers:
    def test_to_datetime_variants(self):
        dt = datetime(2026, 1, 1, tzinfo=timezone.utc)
        assert analysis._to_datetime(dt) is dt
        assert analysis._to_datetime("2026-01-01T12:00:00+00:00") == dt.replace(
            hour=12
        )
        with pytest.raises(TypeError):
            analysis._to_datetime(12345)

    def test_reference_now_empty_uses_now(self):
        ref = analysis.get_reference_now([])
        assert isinstance(ref, datetime)

    def test_reference_now_picks_max(self):
        rows = [
            {"detected_at": datetime(2026, 1, 1, tzinfo=timezone.utc)},
            {"detected_at": "2026-02-01T00:00:00+00:00"},
        ]
        assert analysis.get_reference_now(rows) == datetime(
            2026, 2, 1, tzinfo=timezone.utc
        )

    def test_age_score_buckets(self):
        ref = datetime(2026, 5, 1, 12, tzinfo=timezone.utc)
        assert analysis.get_age_score("2026-04-29T12:00:00+00:00", ref) == 3
        assert analysis.get_age_score("2026-04-30T12:00:00+00:00", ref) == 2
        assert analysis.get_age_score("2026-05-01T06:00:00+00:00", ref) == 1
        assert analysis.get_age_score("2026-05-01T11:00:00+00:00", ref) == 0

    def test_rank_algorithm_orders_critical_first(self):
        rows = [
            {
                "anomaly_type": "A7",
                "severity": "WARNING",
                "transaction_id": None,
                "detected_at": "2026-05-01T11:00:00+00:00",
            },
            {
                "anomaly_type": "A1",
                "severity": "CRITICAL",
                "transaction_id": "tx1",
                "detected_at": "2026-05-01T11:30:00+00:00",
            },
        ]
        ranked = analysis.rank_algorithm(rows)
        assert ranked[0]["anomaly_type"] == "A1"
        assert "issue_score" in ranked[0]

    def test_rank_algorithm_empty(self):
        assert analysis.rank_algorithm([]) == []

    def test_classifier_description_known_and_unknown(self):
        exp, impact, rec = analysis._build_classifier_description(
            "A3", "ATM-1", 0.9, -0.5
        )
        assert isinstance(exp, str) and impact and rec
        exp2, _, _ = analysis._build_classifier_description("AX", "ATM-1", 0.5, 0.1)
        assert "AX" in exp2

    def test_time_window(self):
        start, end = analysis.time_window("2026-05-01T12:00:00+00:00", 3600)
        assert start < end

    def test_detail_functions_smoke(self):
        assert analysis.A1("ATM-1", True, 5, True, True)
        assert analysis.A2("ATM-1", 1, 2, True, False, 0)
        assert analysis.A3(80.0, 95.0, 10, 50, True, True)
        assert analysis.A4(5, 3, 10)
        assert analysis.A5("ATM-1", 900, 0.1, 12, True)
        assert analysis.A6("ATM-1", 70.0, 99.0, 98.0, 5, True)
        assert analysis.A7("ATM-1", 3, True, True)

    def test_query_maps_rows_and_releases(self):
        conn, cur = _cursor(rows=[{"a": 1}])
        with (
            patch.object(analysis, "get_conn", return_value=conn),
            patch.object(analysis, "release_conn") as rel,
        ):
            assert analysis.query("SELECT 1") == [{"a": 1}]
            rel.assert_called_once_with(conn)

    def test_query_release_failure_swallowed(self):
        conn, cur = _cursor(rows=[{"a": 1}])
        with (
            patch.object(analysis, "get_conn", return_value=conn),
            patch.object(
                analysis, "release_conn", side_effect=RuntimeError("pool gone")
            ),
        ):
            assert analysis.query("SELECT 1") == [{"a": 1}]

    def test_main_wires_query_rank_build(self):
        with (
            patch.object(analysis, "query", return_value=[{"x": 1}]),
            patch.object(analysis, "rank_algorithm", return_value=[{"x": 1}]),
            patch.object(analysis, "build_detailed_table", return_value=[{"y": 2}]),
        ):
            assert analysis.main() == [{"y": 2}]

    def test_build_detailed_table_branches(self):
        rows = [
            {
                "anomaly_type": "A1",
                "atm_id": "ATM-1",
                "severity": "CRITICAL",
                "issue_score": 9,
                "detected_at": "2026-05-01T11:00:00+00:00",
                "transaction_id": "t1",
                "confidence": 0.9,
                "if_score": -0.8,
                "title": "t",
                "explanation": "e",
            },
            {
                "anomaly_type": "UNKNOWN",
                "atm_id": "ATM-2",
                "severity": "WARNING",
                "issue_score": 2,
                "detected_at": datetime(2026, 5, 1, 10, tzinfo=timezone.utc),
                "transaction_id": None,
                "confidence": 0.4,
                "if_score": 0.2,
                "title": "t2",
                "explanation": {"k": "v"},
            },
        ]
        out = analysis.build_detailed_table(rows)
        assert len(out) == 2

    def test_build_detailed_table_all_types(self):
        import json as _json

        def row(code, explanation="{}", detected_at="2026-05-01T11:00:00+00:00"):
            return {
                "anomaly_type": code,
                "atm_id": "ATM-1",
                "severity": "CRITICAL",
                "issue_score": 7,
                "detected_at": detected_at,
                "title": f"{code} title",
                "explanation": explanation,
            }

        classifier = _json.dumps(
            {"source": "CLASSIFIER", "confidence": 0.93, "if_score": -0.71}
        )
        rows = [
            row("A2"),
            row("A3"),
            row("A3", classifier),
            row("A4"),
            row("A5"),
            row("A5", classifier),
            row("A6"),
            row("A7"),
            row("UNKNOWN", _json.dumps({"source": "ZSCORE", "max_z_score": 4.5,
                                        "n_features_deviating": 3})),
            row("UNKNOWN", _json.dumps({"if_score": -0.8, "xgb_predicted": "A1",
                                        "xgb_confidence": 0.4})),
        ]
        out = analysis.build_detailed_table(rows)
        assert len(out) == len(rows)
        by_code = {}
        for r in out:
            by_code.setdefault(r["Anomaly"], []).append(r)
        assert set(by_code) == {"A2", "A3", "A4", "A5", "A6", "A7", "UNKNOWN"}
        assert "4.50" in by_code["UNKNOWN"][0]["root_cause"]
        assert all(r["Event_Time"] for r in out)


class TestAnalysisRouter:
    def test_detailed_success_and_none(self):
        client = _analysis_client()
        with patch.object(analysis_router, "run_analysis", return_value=[{"a": 1}]):
            assert client.get("/analysis/detailed").json() == {"data": [{"a": 1}]}
        with patch.object(analysis_router, "run_analysis", return_value=None):
            assert client.get("/analysis/detailed").json() == {"data": []}

    def test_detailed_failure(self):
        client = _analysis_client()
        with patch.object(
            analysis_router, "run_analysis", side_effect=RuntimeError("down")
        ):
            assert client.get("/analysis/detailed").status_code == 500

    def test_metrics_success_and_failure(self):
        client = _analysis_client()
        with (
            patch.object(
                analysis_router,
                "get_time_bucketed_anomalies",
                return_value=[{"b": 1}],
            ),
            patch.object(
                analysis_router, "get_anomaly_summary", return_value={"t": 2}
            ),
        ):
            resp = client.get(
                "/analysis/metrics?hours=24&bucket_minutes=60&anomaly_type=A1&severity=CRITICAL&is_active=1"
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["time_series"] == [{"b": 1}]
            assert body["parameters"]["anomaly_type"] == "A1"
        with patch.object(
            analysis_router,
            "get_time_bucketed_anomalies",
            side_effect=RuntimeError("down"),
        ):
            assert client.get("/analysis/metrics").status_code == 500


class TestAnalyticsEventsMetrics:
    def test_events_with_sources_and_markers(self):
        client = _analytics_client()
        event_rows = [
            {
                "bucket_start": datetime(2026, 1, 1, 12, tzinfo=timezone.utc),
                "source": "ATM_APP",
                "count": 5,
            },
            {"bucket_start": "raw-bucket", "source": "HARDWARE", "count": 2},
        ]
        anomaly_rows = [
            {
                "bucket_start": datetime(2026, 1, 1, 12, tzinfo=timezone.utc),
                "anomaly_type": "A1",
                "severity": "CRITICAL",
            },
            {"bucket_start": "other", "anomaly_type": "A2", "severity": "MAJOR"},
        ]
        conn, cur = _cursor(rows_seq=[event_rows, anomaly_rows])
        with (
            patch.object(analytics_router, "get_conn", return_value=conn),
            patch.object(analytics_router, "release_conn"),
        ):
            resp = client.get(
                "/api/analytics/events?sources=atm_app,, HARDWARE&hours=24"
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["parameters"]["sources"] == ["ATM_APP", "HARDWARE"]
            buckets = {b["bucket_start"]: b for b in body["time_series"]}
            key = datetime(2026, 1, 1, 12, tzinfo=timezone.utc).isoformat()
            assert buckets[key]["anomaly_markers"] == [
                {"type": "A1", "severity": "CRITICAL"}
            ]

    def test_events_hours_zero_and_failure(self):
        client = _analytics_client()
        conn, cur = _cursor(rows_seq=[[], []])
        with (
            patch.object(analytics_router, "get_conn", return_value=conn),
            patch.object(analytics_router, "release_conn"),
        ):
            resp = client.get("/api/analytics/events?hours=0")
            assert resp.status_code == 200
            assert resp.json()["parameters"]["sources"] == [
                "ATM_APP",
                "HARDWARE",
                "TERMINAL_HANDLER",
            ]
        with (
            patch.object(analytics_router, "get_conn", return_value=_failing_conn()),
            patch.object(analytics_router, "release_conn"),
        ):
            body = client.get("/api/analytics/events").json()
            assert body["time_series"] == [] and "error" in body

    def test_metrics_timeline_with_none_avg(self):
        client = _analytics_client()
        metric_rows = [
            {
                "bucket_start": datetime(2026, 1, 1, 12, tzinfo=timezone.utc),
                "source": "KAFKA",
                "metric_name": "cpu",
                "avg_value": None,
            },
            {
                "bucket_start": "raw",
                "source": "KAFKA",
                "metric_name": "mem",
                "avg_value": 1.234,
            },
        ]
        anomaly_rows = [
            {"bucket_start": "raw", "anomaly_type": "A3", "severity": "MAJOR"}
        ]
        conn, cur = _cursor(rows_seq=[metric_rows, anomaly_rows])
        with (
            patch.object(analytics_router, "get_conn", return_value=conn),
            patch.object(analytics_router, "release_conn"),
        ):
            resp = client.get("/api/analytics/metrics?sources=KAFKA&hours=0")
            assert resp.status_code == 200
            buckets = {b["bucket_start"]: b for b in resp.json()["time_series"]}
            assert buckets["raw"]["metrics"]["KAFKA"]["mem"] == 1.23
            assert buckets["raw"]["anomaly_markers"] == [
                {"type": "A3", "severity": "MAJOR"}
            ]

    def test_metrics_timeline_defaults(self):
        from datetime import timezone as _tz

        client = _analytics_client()
        metric_rows = [
            {
                "bucket_start": datetime(2026, 1, 1, 12, tzinfo=_tz.utc),
                "source": "KAFKA",
                "metric_name": "cpu",
                "avg_value": 2.5,
            },
        ]
        conn, cur = _cursor(rows_seq=[metric_rows, []])
        with (
            patch.object(analytics_router, "get_conn", return_value=conn),
            patch.object(analytics_router, "release_conn"),
        ):
            resp = client.get("/api/analytics/metrics")
            assert resp.status_code == 200
            assert resp.json()["parameters"]["sources"] == [
                "KAFKA",
                "PROMETHEUS",
                "OS",
                "CLOUD",
            ]

    def test_metrics_timeline_failure(self):
        client = _analytics_client()
        with (
            patch.object(analytics_router, "get_conn", return_value=_failing_conn()),
            patch.object(analytics_router, "release_conn"),
        ):
            assert "error" in client.get("/api/analytics/metrics").json()

    def test_available_metrics(self):
        client = _analytics_client()
        conn, cur = _cursor(rows=[{"metric_name": "cpu"}])
        with (
            patch.object(analytics_router, "get_conn", return_value=conn),
            patch.object(analytics_router, "release_conn"),
        ):
            assert client.get("/api/analytics/metrics/list").json() == {
                "metrics": ["cpu"]
            }
        with (
            patch.object(analytics_router, "get_conn", return_value=_failing_conn()),
            patch.object(analytics_router, "release_conn"),
        ):
            assert client.get("/api/analytics/metrics/list").json()["metrics"] == []


class TestAnalyticsCounters:
    def test_counters_no_redis(self):
        with patch.object(analytics_router, "get_redis_client", return_value=None):
            assert analytics_router.increment_event_counter("S", "h") is None
            assert analytics_router.increment_anomaly_counter("A1", "h") is None
            assert analytics_router.track_unique_atm("ATM-1") is None
            assert analytics_router.get_unique_atm_count() == 0

    def test_counters_redis_success_and_failure(self):
        client = MagicMock()
        with patch.object(
            analytics_router, "get_redis_client", return_value=client
        ):
            analytics_router.increment_event_counter("ATM_APP", "2026-01-01T12")
            analytics_router.increment_anomaly_counter("A1", "2026-01-01T12")
            analytics_router.track_unique_atm("ATM-1")
            client.pfcount.return_value = 7
            assert analytics_router.get_unique_atm_count() == 7
        bad = MagicMock()
        bad.incr.side_effect = RuntimeError("x")
        bad.zincrby.side_effect = RuntimeError("x")
        bad.pfadd.side_effect = RuntimeError("x")
        bad.pfcount.side_effect = RuntimeError("x")
        with patch.object(analytics_router, "get_redis_client", return_value=bad):
            assert analytics_router.increment_event_counter("S", "h") is None
            assert analytics_router.increment_anomaly_counter("A1", "h") is None
            assert analytics_router.track_unique_atm("ATM-1") is None
            assert analytics_router.get_unique_atm_count() == 0


class TestRealtimeStats:
    def _db(self, events=(), metrics=(), anomalies=(), atms=({"cnt": 3},)):
        cur = MagicMock()
        cur.fetchall.side_effect = [list(events), list(metrics), list(anomalies)]
        cur.fetchone.return_value = atms[0] if atms else None
        ctx = MagicMock()
        ctx.__enter__.return_value = cur
        ctx.__exit__.return_value = False
        conn = MagicMock()
        conn.cursor.return_value = ctx
        return conn

    def test_redis_counters_with_filters(self):
        from datetime import timezone as _tz

        client = _analytics_client()
        hour = datetime.now(_tz.utc).strftime("%Y-%m-%dT%H")
        redis = MagicMock()
        redis.keys.side_effect = [
            [f"stats:events:KAFKA:{hour}", "stats:events:OLD:nope"],
            [f"stats:anomaly:type:{hour}", "stats:anomaly:type:bogus"],
        ]
        redis.get.side_effect = ["4", "1"]
        redis.zrange.side_effect = [[("A1", 2.0)], []]
        atms_conn = self._db()
        with (
            patch.object(analytics_router, "get_redis_client", return_value=redis),
            patch.object(
                analytics_router, "get_conn", return_value=atms_conn
            ),
            patch.object(analytics_router, "release_conn"),
        ):
            body = client.get("/api/analytics/stats/realtime?hours=24").json()
            assert body["events_by_source"]["KAFKA"] == 4
            assert body["anomaly_types"]["A1"] == 2
            assert body["unique_atms"] == 3

    def test_redis_malformed_keys_skipped(self):
        from datetime import timezone as _tz

        client = _analytics_client()
        hour = datetime.now(_tz.utc).strftime("%Y-%m-%dT%H")
        redis = MagicMock()
        redis.keys.side_effect = [
            ["stats:events:KAFKA:not-a-date", f"stats:events:KAFKA:{hour}"],
            [],
        ]
        redis.get.side_effect = ["9", None]
        atms_conn = self._db()
        with (
            patch.object(analytics_router, "get_redis_client", return_value=redis),
            patch.object(analytics_router, "get_conn", return_value=atms_conn),
            patch.object(analytics_router, "release_conn"),
        ):
            body = client.get("/api/analytics/stats/realtime?hours=24").json()
            assert body["events_by_source"] == {}

    def test_db_fallback_all_time(self):
        client = _analytics_client()
        conn = self._db(
            events=[{"source": "ATM_APP", "cnt": 5}],
            metrics=[{"source": "KAFKA", "cnt": 2}],
            anomalies=[{"anomaly_type": "A1", "cnt": 7}],
        )
        with (
            patch.object(analytics_router, "get_redis_client", return_value=None),
            patch.object(analytics_router, "get_conn", return_value=conn),
            patch.object(analytics_router, "release_conn"),
        ):
            body = client.get("/api/analytics/stats/realtime?hours=0").json()
            assert body["events_by_source"] == {"ATM_APP": 5, "KAFKA": 2}
            assert body["anomaly_types"] == {"A1": 7}

    def test_db_fallback_bounded_and_atms_failure(self):
        client = _analytics_client()
        conn = self._db(events=[{"source": "S", "cnt": 1}])
        fail_conn = MagicMock()
        fail_ctx = MagicMock()
        fail_ctx.__enter__.side_effect = RuntimeError("atms down")
        fail_conn.cursor.return_value = fail_ctx
        with (
            patch.object(analytics_router, "get_redis_client", return_value=None),
            patch.object(
                analytics_router, "get_conn", side_effect=[conn, fail_conn]
            ),
            patch.object(analytics_router, "release_conn"),
        ):
            body = client.get("/api/analytics/stats/realtime?hours=5").json()
            assert body["events_by_source"]["S"] >= 1
            assert body["unique_atms"] == 0

    def test_entities_success_and_failure(self):
        client = _analytics_client()
        conn, cur = _cursor(rows=[{"atm_id": "ATM-1"}])
        with (
            patch.object(analytics_router, "get_conn", return_value=conn),
            patch.object(analytics_router, "release_conn"),
        ):
            assert client.get("/api/analytics/entities").json() == {
                "entities": [{"atm_id": "ATM-1"}]
            }
        with (
            patch.object(analytics_router, "get_conn", return_value=_failing_conn()),
            patch.object(analytics_router, "release_conn"),
        ):
            assert client.get("/api/analytics/entities").json() == {"entities": []}

    def test_realtime_stale_hour_keys_skipped(self):
        from datetime import timezone as _tz

        client = _analytics_client()
        hour = datetime.now(_tz.utc).strftime("%Y-%m-%dT%H")
        redis = MagicMock()
        redis.keys.side_effect = [
            [f"stats:events:KAFKA:{hour}", "stats:events:KAFKA:2020-01-01T00"],
            [f"stats:anomaly:type:{hour}", "stats:anomaly:type:2020-01-01T00"],
        ]
        redis.get.side_effect = ["4", "99"]
        redis.zrange.side_effect = [[("A1", 2.0)], [("A9", 9.0)]]
        atms_conn = self._db()
        with (
            patch.object(analytics_router, "get_redis_client", return_value=redis),
            patch.object(analytics_router, "get_conn", return_value=atms_conn),
            patch.object(analytics_router, "release_conn"),
        ):
            body = client.get("/api/analytics/stats/realtime?hours=24").json()
            assert body["events_by_source"] == {"KAFKA": 4}
            assert body["anomaly_types"] == {"A1": 2}

    def test_realtime_redis_failure_falls_back_to_db(self):
        client = _analytics_client()
        bad_redis = MagicMock()
        bad_redis.keys.side_effect = RuntimeError("redis down")
        conn = self._db(
            events=[{"source": "ATM_APP", "cnt": 5}],
            metrics=[],
            anomalies=[{"anomaly_type": "A1", "cnt": 7}],
        )
        with (
            patch.object(analytics_router, "get_redis_client", return_value=bad_redis),
            patch.object(analytics_router, "get_conn", return_value=conn),
            patch.object(analytics_router, "release_conn"),
        ):
            body = client.get("/api/analytics/stats/realtime?hours=24").json()
            assert body["events_by_source"]["ATM_APP"] == 5
            assert body["anomaly_types"] == {"A1": 7}

    def test_realtime_db_failure_returns_empty(self):
        client = _analytics_client()
        with (
            patch.object(analytics_router, "get_redis_client", return_value=None),
            patch.object(analytics_router, "get_conn", return_value=_failing_conn()),
            patch.object(analytics_router, "release_conn"),
        ):
            body = client.get("/api/analytics/stats/realtime?hours=24").json()
            assert body["events_by_source"] == {}
            assert body["unique_atms"] == 0
