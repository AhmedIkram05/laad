"""Tests for backend.src.analysis.analysis."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest


# ── _to_datetime ──────────────────────────────────────────────────────────

class TestToDatetime:
    def test_passes_datetime_through(self):
        from backend.src.analysis.analysis import _to_datetime
        dt = datetime(2026, 3, 5, 9, 0, 0, tzinfo=timezone.utc)
        assert _to_datetime(dt) is dt

    def test_parses_iso_string(self):
        from backend.src.analysis.analysis import _to_datetime
        result = _to_datetime("2026-03-05T09:15:00+00:00")
        assert result is not None
        assert result.year == 2026


# ── get_age_score ────────────────────────────────────────────────────────

class TestGetAgeScore:
    def test_recent_returns_0(self):
        from backend.src.analysis.analysis import get_age_score
        now = datetime(2026, 3, 5, 12, 0, 0, tzinfo=timezone.utc)
        recent = now - timedelta(hours=1)
        assert get_age_score(recent, now) == 0

    def test_6h_returns_1(self):
        from backend.src.analysis.analysis import get_age_score
        now = datetime(2026, 3, 5, 12, 0, 0, tzinfo=timezone.utc)
        old = now - timedelta(hours=6, minutes=1)
        assert get_age_score(old, now) == 1

    def test_24h_returns_2(self):
        from backend.src.analysis.analysis import get_age_score
        now = datetime(2026, 3, 5, 12, 0, 0, tzinfo=timezone.utc)
        old = now - timedelta(hours=24, minutes=1)
        assert get_age_score(old, now) == 2

    def test_48h_or_more_returns_3(self):
        from backend.src.analysis.analysis import get_age_score
        now = datetime(2026, 3, 5, 12, 0, 0, tzinfo=timezone.utc)
        old = now - timedelta(hours=48, minutes=1)
        assert get_age_score(old, now) == 3

    def test_string_datetime_input(self):
        from backend.src.analysis.analysis import get_age_score
        now = datetime(2026, 3, 5, 12, 0, 0, tzinfo=timezone.utc)
        old_str = "2026-03-05T09:00:00+00:00"
        score = get_age_score(old_str, now)
        assert isinstance(score, int)


# ── time_window ──────────────────────────────────────────────────────────

class TestTimeWindow:
    def test_returns_start_end_strings(self):
        from backend.src.analysis.analysis import time_window
        end = datetime(2026, 3, 5, 12, 0, 0, tzinfo=timezone.utc)
        start_str, end_str = time_window(end, 60)
        assert isinstance(start_str, str)
        assert isinstance(end_str, str)
        assert end_str == "2026-03-05 12:00:00"

    def test_none_endtime_raises_typeerror(self):
        from backend.src.analysis.analysis import time_window
        with pytest.raises(TypeError, match="Unsupported datetime"):
            time_window(None, 60)


# ── A1-A7 detail builders ────────────────────────────────────────────────

class TestA1:
    def test_returns_explanation_impact_recommendation(self):
        from backend.src.analysis.analysis import A1
        result = A1("ATM-001", error_seen=3, max_timeout=30000,
                    kafka_offline=True, terminal_timeout=2)
        assert len(result) == 3
        assert "ATM-001" in result[0]
        assert result[1]
        assert result[2]

    def test_no_errors(self):
        from backend.src.analysis.analysis import A1
        result = A1("ATM-001", error_seen=0, max_timeout=0,
                    kafka_offline=False, terminal_timeout=0)
        assert result[0]


class TestA2:
    def test_returns_explanation_impact_recommendation(self):
        from backend.src.analysis.analysis import A2
        result = A2("ATM-001", low_count=2, empty_count=2,
                    out_of_service=True, dispense_error=True, zero_tps=True)
        assert len(result) == 3
        assert "ATM-001" in result[0]

    def test_no_anomalies(self):
        from backend.src.analysis.analysis import A2
        result = A2("ATM-001", low_count=0, empty_count=0,
                    out_of_service=False, dispense_error=False, zero_tps=False)
        assert result[0]


class TestA3:
    def test_returns_explanation_impact_recommendation(self):
        from backend.src.analysis.analysis import A3
        result = A3(mem_start=300, mem_end=1040, gc_start=0.45,
                    gc_end=24.7, high_cpu=0.94, oom_seen=True)
        assert len(result) == 3

    def test_no_oom(self):
        from backend.src.analysis.analysis import A3
        result = A3(mem_start=300, mem_end=500, gc_start=0.45,
                    gc_end=1.0, high_cpu=0.5, oom_seen=False)
        assert result[0]


class TestA4:
    def test_returns_explanation_impact_recommendation(self):
        from backend.src.analysis.analysis import A4
        result = A4(max_restart=2, fatal_count=2, startup_count=3)
        assert len(result) == 3


class TestA5:
    def test_returns_explanation_impact_recommendation(self):
        from backend.src.analysis.analysis import A5
        result = A5("ATM-001", max_rt=30000, min_success=50,
                    max_failures=14, timeout_seen=True)
        assert len(result) == 3


class TestA6:
    def test_returns_explanation_impact_recommendation(self):
        from backend.src.analysis.analysis import A6
        result = A6("ATM-001", mem_start=46, mem_max=98.75,
                    cpu_max=91.5, net_error_max=22, timeout_seen=True)
        assert len(result) == 3


class TestA7:
    def test_returns_explanation_impact_recommendation(self):
        from backend.src.analysis.analysis import A7
        result = A7("ATM-001", missing_field_count=3,
                    malformed_metric=True, ooo=True)
        assert len(result) == 3


# ── _build_classifier_description ────────────────────────────────────────

class TestBuildClassifierDescription:
    def test_returns_tuple_for_known_type(self):
        from backend.src.analysis.analysis import _build_classifier_description
        result = _build_classifier_description("A3", "ATM-001", 0.95, 0.8)
        assert len(result) == 3
        assert result[0]
        assert result[1]
        assert result[2]

    def test_returns_tuple_for_a4(self):
        from backend.src.analysis.analysis import _build_classifier_description
        result = _build_classifier_description("A4", "ATM-001", 0.85, 0.7)
        assert len(result) == 3

    def test_handles_missing_type(self):
        from backend.src.analysis.analysis import _build_classifier_description
        result = _build_classifier_description("UNKNOWN", "ATM-001", 0.5, 0.0)
        assert len(result) == 3


# ── rank_algorithm ───────────────────────────────────────────────────────

class TestRankAlgorithm:
    def test_empty_list_returns_empty(self):
        from backend.src.analysis.analysis import rank_algorithm
        assert rank_algorithm([]) == []

    def test_returns_sorted_by_score(self):
        from backend.src.analysis.analysis import rank_algorithm
        anomalies = [
            {"anomaly_type": "A1", "severity": "CRITICAL", "detected_at": "2026-03-05T09:00:00+00:00", "transaction_id": None},
            {"anomaly_type": "A7", "severity": "WARNING", "detected_at": "2026-03-05T09:00:00+00:00", "transaction_id": None},
        ]
        result = rank_algorithm(anomalies)
        assert len(result) == 2
        # A1 should be ranked higher (gravity 7) than A7 (gravity 1)
        assert result[0]["anomaly_type"] == "A1"
        assert "issue_score" in result[0]

    def test_score_components(self):
        from backend.src.analysis.analysis import rank_algorithm
        anomalies = [
            {"anomaly_type": "A1", "severity": "CRITICAL", "detected_at": "2026-03-05T09:00:00+00:00", "transaction_id": None},
        ]
        result = rank_algorithm(anomalies)
        item = result[0]
        assert "issue_score" in item
        assert isinstance(item["issue_score"], int)


# ── get_reference_now ────────────────────────────────────────────────────

class TestGetReferenceNow:
    def test_returns_max_detected_at(self):
        from backend.src.analysis.analysis import get_reference_now
        anomalies = [
            {"detected_at": "2026-03-05T09:00:00+00:00"},
            {"detected_at": "2026-03-05T12:00:00+00:00"},
        ]
        ref = get_reference_now(anomalies)
        assert ref.hour == 12


# ── build_detailed_table ─────────────────────────────────────────────────

class TestBuildDetailedTable:
    def test_empty_returns_empty_list(self):
        from backend.src.analysis.analysis import build_detailed_table
        assert build_detailed_table([]) == []

    @patch("backend.src.analysis.analysis.A1")
    def test_dispatches_to_type_handler(self, mock_a1):
        mock_a1.return_value = ("Root cause", "Impact", "Action")
        from backend.src.analysis.analysis import build_detailed_table
        anomalies = [
            {
                "atm_id": "ATM-001",
                "anomaly_type": "A1",
                "explanation": json.dumps({
                    "error_seen": 3,
                    "max_timeout": 30000,
                    "kafka_offline": True,
                    "terminal_timeout": 2,
                }),
                "severity": "CRITICAL",
                "title": "Test A1",
                "detected_at": "2026-03-05T09:00:00+00:00",
                "model_confidence_score": 0.95,
                "is_active": True,
                "issue_score": 10,
            }
        ]
        result = build_detailed_table(anomalies)
        assert len(result) == 1
        assert result[0]["root_cause"] == "Root cause"

    def test_unknown_type(self):
        from backend.src.analysis.analysis import build_detailed_table
        anomalies = [
            {
                "atm_id": "ATM-001",
                "anomaly_type": "UNKNOWN",
                "explanation": "{}",
                "severity": "LOW",
                "title": "Test Unknown",
                "detected_at": "2026-03-05T09:00:00+00:00",
                "model_confidence_score": 0.0,
                "is_active": True,
                "issue_score": 0,
            }
        ]
        result = build_detailed_table(anomalies)
        assert len(result) == 1
        assert "does not match" in result[0]["root_cause"].lower()


import json
