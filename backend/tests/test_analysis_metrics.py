"""Tests for backend.src.analysis.metrics."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest


class TestGetTimeBucketedAnomalies:
    def test_returns_empty_when_no_anomalies(self):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

        with patch("backend.src.analysis.metrics.get_conn", return_value=mock_conn), \
             patch("backend.src.analysis.metrics.release_conn"):
            from backend.src.analysis.metrics import get_time_bucketed_anomalies
            result = get_time_bucketed_anomalies(hours=24, bucket_minutes=60)

        assert result == []

    def test_with_anomaly_type_filter(self):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            {"bucket_start": datetime(2026, 3, 5, 9, 0, tzinfo=timezone.utc),
             "bucket_end": datetime(2026, 3, 5, 10, 0, tzinfo=timezone.utc),
             "anomaly_type": "A1", "count": 3},
        ]
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

        with patch("backend.src.analysis.metrics.get_conn", return_value=mock_conn), \
             patch("backend.src.analysis.metrics.release_conn"):
            from backend.src.analysis.metrics import get_time_bucketed_anomalies
            result = get_time_bucketed_anomalies(hours=24, bucket_minutes=60, anomaly_type="A1")

        assert len(result) == 1
        assert result[0]["total"] == 3

    def test_with_severity_filter(self):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

        with patch("backend.src.analysis.metrics.get_conn", return_value=mock_conn), \
             patch("backend.src.analysis.metrics.release_conn"):
            from backend.src.analysis.metrics import get_time_bucketed_anomalies
            result = get_time_bucketed_anomalies(hours=24, bucket_minutes=60, severity="CRITICAL")

        assert result == []

    def test_with_is_active_filter(self):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

        with patch("backend.src.analysis.metrics.get_conn", return_value=mock_conn), \
             patch("backend.src.analysis.metrics.release_conn"):
            from backend.src.analysis.metrics import get_time_bucketed_anomalies
            result = get_time_bucketed_anomalies(hours=24, bucket_minutes=60, is_active=True)

        assert result == []


class TestGetAnomalySummary:
    def test_returns_summary_dict(self):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        # First fetchone: overall counts
        mock_cursor.fetchone.side_effect = [
            {"total": 100, "active": 60, "resolved": 40,
             "critical": 20, "major": 30, "high": 25, "warning": 25},
        ]
        # fetchall calls: by_type then hourly_trend
        mock_cursor.fetchall.side_effect = [
            [  # by_type
                {"anomaly_type": "A1", "count": 30, "active": 15},
                {"anomaly_type": "A2", "count": 20, "active": 10},
            ],
            [],  # hourly_trend (empty)
        ]
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

        with patch("backend.src.analysis.metrics.get_conn", return_value=mock_conn), \
             patch("backend.src.analysis.metrics.release_conn"):
            from backend.src.analysis.metrics import get_anomaly_summary
            result = get_anomaly_summary()

        assert result["total"] == 100
        assert result["active"] == 60
        assert result["resolved"] == 40
        assert result["critical"] == 20
        assert "by_type" in result
