"""Branch coverage for backend/src/mcp/tools/structured.py.

Loads structured.py directly from file (bypassing the package __init__
which pulls chromadb) and mocks get_cursor with an in-memory fake.
Covers every filter, clamp, error and aggregation branch.
"""

from __future__ import annotations

import importlib.util
import pathlib
from contextlib import contextmanager
from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

_REPO = pathlib.Path(__file__).resolve().parents[3]
_SPEC = importlib.util.spec_from_file_location(
    "mcp_structured_under_test",
    str(_REPO / "backend" / "src" / "mcp" / "tools" / "structured.py"),
)
assert _SPEC and _SPEC.loader
_mod = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_mod)


class FakeCursor:
    def __init__(self, rows=None, one=None):
        self._rows = rows or []
        self._one = one
        self.sql = ""
        self.params = None
        self.executions = []

    def execute(self, sql, params=None):
        self.sql = sql
        self.params = list(params) if params is not None else None
        self.executions.append((sql, self.params))

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._one


@contextmanager
def _cursor(monkeypatch, rows=None, one=None, zweiten_one=None):
    """Fake get_cursor. zweiten_one handles get_statistics' 2nd execute."""
    cur = FakeCursor(rows=rows, one=one)

    if zweiten_one is not None:
        calls = {"n": 0}
        orig_exec = cur.execute

        def _exec(sql, params=None):
            orig_exec(sql, params)
            calls["n"] += 1
            if calls["n"] == 2:
                cur._one = zweiten_one

        cur.execute = _exec  # type: ignore[method-assign]

    ctx = MagicMock()
    ctx.__enter__.return_value = cur
    ctx.__exit__.return_value = False
    monkeypatch.setattr(_mod, "get_cursor", lambda *a, **k: ctx)
    yield cur


class TestJsonSafe:
    def test_datetime_decimal_passthrough(self):
        dt = datetime(2026, 3, 5, 9, 15, 0)
        out = _mod._json_safe({"a": dt, "b": Decimal("1.5"), "c": "x", "d": None})
        assert out["a"] == dt.isoformat()
        assert out["b"] == pytest.approx(1.5)
        assert out["c"] == "x"
        assert out["d"] is None

    def test_rows_maps_fetchall(self):
        cur = FakeCursor(rows=[{"x": 1}, {"x": 2}])
        assert _mod._rows(cur) == [{"x": 1}, {"x": 2}]


class TestQueryAnomalies:
    def test_no_filters(self, monkeypatch):
        with _cursor(monkeypatch, rows=[]) as cur:
            out = _mod.query_anomalies()
            assert out == {"rows": [], "count": 0}
            assert "WHERE" not in cur.sql
            assert cur.params == [100]

    def test_all_filters(self, monkeypatch):
        rows = [{"id": 1, "detected_at": datetime(2026, 1, 1)}]
        with _cursor(monkeypatch, rows=rows) as cur:
            out = _mod.query_anomalies(
                atm_id="ATM-1",
                anomaly_type="A3",
                severity="CRITICAL",
                limit=5,
                is_active=True,
                start="2026-01-01T00:00:00+00:00",
                end="2026-02-01T00:00:00+00:00",
            )
            assert out["count"] == 1
            for frag in (
                "atm_id = %s",
                "anomaly_type = %s",
                "severity = %s",
                "is_active = %s",
                "detected_at >=",
                "detected_at <=",
            ):
                assert frag in cur.sql
            assert cur.params[:-1] == [
                "ATM-1",
                "A3",
                "CRITICAL",
                1,
                "2026-01-01T00:00:00+00:00",
                "2026-02-01T00:00:00+00:00",
            ]

    def test_is_active_false_and_limit_clamps(self, monkeypatch):
        with _cursor(monkeypatch, rows=[]) as cur:
            _mod.query_anomalies(is_active=False, limit=0)
            assert 0 in cur.params  # False -> 0
            assert cur.params[-1] == 1  # max(1, min(0,500))
        with _cursor(monkeypatch, rows=[]) as cur:
            _mod.query_anomalies(limit=9999)
            assert cur.params[-1] == 500


class TestGetAnomaly:
    def test_found_string_id(self, monkeypatch):
        row = {"id": 7, "title": "t", "detected_at": datetime(2026, 1, 2)}
        with _cursor(monkeypatch, one=row) as cur:
            out = _mod.get_anomaly("7")
            assert out["id"] == 7
            assert out["detected_at"] == row["detected_at"].isoformat()
            assert cur.params == [7]

    def test_not_found(self, monkeypatch):
        with _cursor(monkeypatch, one=None):
            out = _mod.get_anomaly(999)
            assert "not found" in out["error"]


class TestMachineHistory:
    def test_clamps_and_params(self, monkeypatch):
        with _cursor(monkeypatch, rows=[]) as cur:
            out = _mod.get_machine_history("ATM-1", hours=0, limit=9999)
            assert out == {"rows": [], "count": 0}
            assert cur.params == ["ATM-1", "1 hours", "ATM-1", "1 hours", 500]

    def test_upper_hours_clamp(self, monkeypatch):
        with _cursor(monkeypatch, rows=[]) as cur:
            _mod.get_machine_history("ATM-1", hours=24 * 365, limit=10)
            assert cur.params[1] == f"{24 * 30} hours"


class TestAtmMetrics:
    def test_no_optional_filters(self, monkeypatch):
        with _cursor(monkeypatch, rows=[]) as cur:
            _mod.get_atm_metrics("E1")
            assert "entity_id = %s" in cur.sql
            assert "metric_name = %s" not in cur.sql
            assert cur.params == ["E1", 500]

    def test_all_filters_and_clamp(self, monkeypatch):
        with _cursor(monkeypatch, rows=[{"metric_name": "m"}]) as cur:
            out = _mod.get_atm_metrics(
                "E1", metric_name="cpu", start="s", end="e", limit=0
            )
            assert out["count"] == 1
            assert "metric_name = %s" in cur.sql
            assert cur.params == ["E1", "cpu", "s", "e", 1]

    def test_limit_upper_clamp(self, monkeypatch):
        with _cursor(monkeypatch, rows=[]) as cur:
            _mod.get_atm_metrics("E1", limit=5000)
            assert cur.params[-1] == 1000


class TestStatistics:
    def test_invalid_group_by(self):
        out = _mod.get_statistics(group_by="os_version; DROP TABLE anomalies")
        assert "error" in out

    def test_no_filters(self, monkeypatch):
        groups = [{"group_key": "A1", "count": 2}]
        totals = {"total": 2, "active": 1, "resolved": 1}
        with _cursor(monkeypatch, rows=groups, zweiten_one=totals) as cur:
            out = _mod.get_statistics()
            assert out["groups"] == [{"group": "A1", "count": 2}]
            assert out["total"] == 2
            assert "WHERE" not in cur.executions[0][0]

    def test_hours_and_active_filters(self, monkeypatch):
        with _cursor(
            monkeypatch, rows=[], zweiten_one={"total": 0, "active": 0, "resolved": 0}
        ) as cur:
            _mod.get_statistics(hours=48, group_by="severity", is_active=False)
            sql = cur.executions[0][0]
            assert "detected_at >=" in sql
            assert "is_active = %s" in sql
            assert cur.executions[0][1] == ["48 hours", 0]

    def test_hours_clamped(self, monkeypatch):
        with _cursor(
            monkeypatch, rows=[], zweiten_one={"total": 0, "active": 0, "resolved": 0}
        ) as cur:
            _mod.get_statistics(hours=24 * 400)
            assert cur.executions[0][1] == [f"{24 * 365} hours"]


class TestSearchEvents:
    def test_no_filters_uses_true(self, monkeypatch):
        with _cursor(monkeypatch, rows=[]) as cur:
            out = _mod.search_events()
            assert out == {"rows": [], "count": 0}
            assert "TRUE" in cur.sql

    def test_all_filters(self, monkeypatch):
        rows = [{"id": 1, "message": "hi"}]
        with _cursor(monkeypatch, rows=rows) as cur:
            out = _mod.search_events(
                source="OS", atm_id="A1", severity="ERROR", start="s", end="e", limit=5
            )
            assert out["count"] == 1
            for frag in ("source = %s", "atm_id = %s", "severity = %s"):
                assert frag in cur.sql

    def test_long_message_truncated(self, monkeypatch):
        rows = [{"id": 1, "message": "x" * 600}]
        with _cursor(monkeypatch, rows=rows):
            out = _mod.search_events()
            assert out["rows"][0]["message"].endswith("...")
            assert len(out["rows"][0]["message"]) == 503

    def test_short_and_missing_message(self, monkeypatch):
        rows = [{"id": 1, "message": "short"}, {"id": 2}]
        with _cursor(monkeypatch, rows=rows):
            out = _mod.search_events()
            assert out["rows"][0]["message"] == "short"
            assert "message" not in out["rows"][1]

    def test_limit_clamps(self, monkeypatch):
        with _cursor(monkeypatch, rows=[]) as cur:
            _mod.search_events(limit=0)
            assert cur.params[-1] == 1
        with _cursor(monkeypatch, rows=[]) as cur:
            _mod.search_events(limit=9999)
            assert cur.params[-1] == 500


class TestErrorContext:
    def test_neither_id(self):
        assert "error" in _mod.get_error_context()

    def test_both_ids(self):
        out = _mod.get_error_context(correlation_id="c", transaction_id="t")
        assert "exactly one" in out["error"]

    def test_correlation(self, monkeypatch):
        with _cursor(monkeypatch, rows=[{"id": 1}]) as cur:
            out = _mod.get_error_context(correlation_id="corr-1", limit=10)
            assert out["count"] == 1
            assert cur.params == ["corr-1", "corr-1", 10]

    def test_transaction_limit_clamp(self, monkeypatch):
        with _cursor(monkeypatch, rows=[]) as cur:
            _mod.get_error_context(transaction_id="tx-1", limit=9999)
            assert cur.params[-1] == 500


class TestAtmInfo:
    def test_found(self, monkeypatch):
        with _cursor(monkeypatch, one={"os_version": "v1", "location_code": "L1"}):
            out = _mod.get_atm_info("ATM-1")
            assert out == {"atm_id": "ATM-1", "os_version": "v1", "location_code": "L1"}

    def test_not_found(self, monkeypatch):
        with _cursor(monkeypatch, one=None):
            out = _mod.get_atm_info("ATM-NOPE")
            assert "not found" in out["error"]


class TestCompareAtms:
    def test_metric_branch(self, monkeypatch):
        rows = [
            {"atm_id": "A1", "avg_value": 10.0},
            {"atm_id": "A2", "avg_value": 12.0},
        ]
        with _cursor(monkeypatch, rows=rows) as cur:
            out = _mod.compare_atms(metric_name="cpu_usage_percent", hours=24, limit=20)
            assert len(out["rows"]) == 2
            assert "metric_name = %s" in cur.sql
            assert out["overall_mean"] == pytest.approx(11.0)
            assert out["outliers"] == []

    def test_anomaly_branch_with_type(self, monkeypatch):
        rows = [{"atm_id": "A1", "anomaly_count": 3, "avg_confidence": 0.9}]
        with _cursor(monkeypatch, rows=rows) as cur:
            out = _mod.compare_atms(anomaly_type="A3")
            assert out["rows"] == rows
            assert "anomaly_type = %s" in cur.sql

    def test_anomaly_branch_no_type(self, monkeypatch):
        with _cursor(monkeypatch, rows=[]) as cur:
            out = _mod.compare_atms()
            assert out == {
                "rows": [],
                "overall_mean": 0.0,
                "overall_std": 0.0,
                "outliers": [],
            }
            assert "anomaly_type" not in cur.sql

    def test_outlier_detection(self, monkeypatch):
        rows = [{"atm_id": f"A{i}", "avg_value": 10.0} for i in range(10)]
        rows.append({"atm_id": "OUT", "avg_value": 1000.0})
        with _cursor(monkeypatch, rows=rows):
            out = _mod.compare_atms(metric_name="m")
            assert out["outliers"] == ["OUT"]

    def test_std_zero_no_outliers(self, monkeypatch):
        rows = [{"atm_id": "A1", "avg_value": 5.0}, {"atm_id": "A2", "avg_value": 5.0}]
        with _cursor(monkeypatch, rows=rows):
            out = _mod.compare_atms(metric_name="m")
            assert out["overall_std"] == pytest.approx(0.0)
            assert out["outliers"] == []

    def test_clamps(self, monkeypatch):
        with _cursor(monkeypatch, rows=[]) as cur:
            _mod.compare_atms(hours=0, limit=0)
            assert cur.params[-1] == 1
