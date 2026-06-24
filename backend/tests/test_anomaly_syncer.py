"""Tests for backend.kafka.anomaly_syncer."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def sample_anomaly():
    return {
        "id": 1,
        "atm_id": "ATM-GB-0001",
        "anomaly_type": "A1",
        "title": "Network Timeout Cascade",
        "severity": "CRITICAL",
        "explanation": '{"signals": ["NETWORK_DISCONNECT"]}',
        "detected_at": datetime(2026, 3, 5, 9, 15, tzinfo=timezone.utc),
    }


class TestAnomalySyncerInit:
    def test_init_sets_empty_synced_ids(self):
        with patch("backend.kafka.anomaly_syncer.ChromaBuffer") as mock_buffer:  # noqa: F841
            from backend.kafka.anomaly_syncer import AnomalySyncer  # noqa: E402

            syncer = AnomalySyncer()
        assert syncer._synced_ids == set()

    def test_init_chroma_failure_graceful(self):
        with patch(
            "backend.kafka.anomaly_syncer.ChromaBuffer",
            side_effect=Exception("Chroma unavailable"),
        ):
            from backend.kafka.anomaly_syncer import AnomalySyncer

            syncer = AnomalySyncer()
        assert syncer._chroma_buffer is None


class TestFormatAnomalyText:
    def test_format_includes_type_and_atm(self, sample_anomaly):
        with patch("backend.kafka.anomaly_syncer.ChromaBuffer"):
            from backend.kafka.anomaly_syncer import AnomalySyncer

            syncer = AnomalySyncer()
            text = syncer._format_anomaly_text(sample_anomaly)

        assert "[A1]" in text
        assert "ATM-GB-0001" in text
        assert "Network Timeout Cascade" in text


class TestGetUnsyncedAnomalies:
    def test_returns_list_of_anomalies(self):
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            {
                "id": 1,
                "detected_at": "2026-03-05T09:15:00+00:00",
                "anomaly_type": "A1",
                "atm_id": "ATM-GB-0001",
                "severity": "CRITICAL",
                "title": "Test",
                "explanation": "{}",
            }
        ]
        mock_cursor.description = [("id",)]

        with patch("backend.kafka.anomaly_syncer.get_cursor") as mock_get_cursor:
            mock_get_cursor.return_value.__enter__.return_value = mock_cursor
            with patch("backend.kafka.anomaly_syncer.ChromaBuffer"):
                from backend.kafka.anomaly_syncer import AnomalySyncer

                syncer = AnomalySyncer()
                anomalies = syncer._get_unsynced_anomalies()

        assert len(anomalies) == 1


class TestSyncOnce:
    def test_sync_once_no_new_anomalies(self):
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []
        mock_cursor.description = [("id",)]

        with patch("backend.kafka.anomaly_syncer.get_cursor") as mock_get_cursor:
            mock_get_cursor.return_value.__enter__.return_value = mock_cursor
            with patch("backend.kafka.anomaly_syncer.ChromaBuffer"):
                from backend.kafka.anomaly_syncer import AnomalySyncer

                syncer = AnomalySyncer()
                result = syncer.sync_once()

        assert result["status"] == "no_new_anomalies"

    def test_sync_once_with_anomalies(self):
        mock_cursor = MagicMock()
        ts = datetime(2026, 3, 5, 9, 15, tzinfo=timezone.utc)
        mock_cursor.fetchall.return_value = [
            {
                "id": 1,
                "detected_at": ts,
                "anomaly_type": "A1",
                "atm_id": "ATM-GB-0001",
                "severity": "CRITICAL",
                "title": "Test",
                "explanation": "{}",
            }
        ]
        mock_cursor.description = [
            ("id",),
            ("detected_at",),
            ("anomaly_type",),
            ("atm_id",),
            ("severity",),
            ("title",),
            ("explanation",),
        ]

        with patch("backend.kafka.anomaly_syncer.get_cursor") as mock_get_cursor:
            mock_get_cursor.return_value.__enter__.return_value = mock_cursor
            with patch("backend.kafka.anomaly_syncer.ChromaBuffer") as mock_cls:
                mock_buffer = MagicMock()
                mock_cls.return_value = mock_buffer
                from backend.kafka.anomaly_syncer import AnomalySyncer

                syncer = AnomalySyncer()
                result = syncer.sync_once()

        assert result["status"] == "success"
        assert result["synced"] >= 1

    def test_sync_once_chroma_unavailable(self):
        ts = datetime(2026, 3, 5, 9, 15, tzinfo=timezone.utc)
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            {
                "id": 1,
                "detected_at": ts,
                "anomaly_type": "A1",
                "atm_id": "ATM-GB-0001",
                "severity": "CRITICAL",
                "title": "Test",
                "explanation": "{}",
            }
        ]
        mock_cursor.description = [
            ("id",),
            ("detected_at",),
            ("anomaly_type",),
            ("atm_id",),
            ("severity",),
            ("title",),
            ("explanation",),
        ]

        with patch("backend.kafka.anomaly_syncer.get_cursor") as mock_get_cursor:
            mock_get_cursor.return_value.__enter__.return_value = mock_cursor
            with patch("backend.kafka.anomaly_syncer.ChromaBuffer") as mock_cls:
                mock_buffer = MagicMock()
                mock_buffer.add_event.side_effect = Exception("Chroma error")
                mock_cls.return_value = mock_buffer
                from backend.kafka.anomaly_syncer import AnomalySyncer

                syncer = AnomalySyncer()
                result = syncer.sync_once()

        assert result["status"] == "success"
