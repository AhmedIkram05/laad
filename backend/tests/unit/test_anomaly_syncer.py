"""Tests for backend.kafka.anomaly_syncer."""

from __future__ import annotations

from contextlib import contextmanager
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
            with (
                patch(
                    "backend.kafka.anomaly_syncer.get_redis_client", return_value=None
                ),
                patch("backend.kafka.anomaly_syncer.ChromaBuffer"),
            ):
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
            with (
                patch(
                    "backend.kafka.anomaly_syncer.get_redis_client", return_value=None
                ),
                patch("backend.kafka.anomaly_syncer.ChromaBuffer") as mock_cls,
            ):
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
            with (
                patch(
                    "backend.kafka.anomaly_syncer.get_redis_client", return_value=None
                ),
                patch("backend.kafka.anomaly_syncer.ChromaBuffer") as mock_cls,
            ):
                mock_buffer = MagicMock()
                mock_buffer.add_event.side_effect = Exception("Chroma error")
                mock_cls.return_value = mock_buffer
                from backend.kafka.anomaly_syncer import AnomalySyncer

                syncer = AnomalySyncer()
                result = syncer.sync_once()

        assert result["status"] == "success"


class _FakeRedis:
    """Minimal stand-in for the redis client: keys live in a set."""

    def __init__(self):
        self.keys = set()

    def exists(self, key):
        return 1 if key in self.keys else 0

    def set(self, key, value, ex=None):
        self.keys.add(key)
        return True


def _row(anomaly_id=1):
    return {
        "id": anomaly_id,
        "detected_at": datetime(2026, 3, 5, 9, 15, tzinfo=timezone.utc),
        "anomaly_type": "A1",
        "atm_id": "ATM-GB-0001",
        "severity": "CRITICAL",
        "title": "Test",
        "explanation": "{}",
    }


class TestSyncStatePersistence:
    """Audit finding #5: None-ATM rows never synced; sync state survives
    restarts via Redis (no duplicate re-syncs); no unbounded NOT IN clause."""

    @staticmethod
    @contextmanager
    def _syncer_with_rows(redis_client, rows):
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = rows
        mock_cursor.description = [("id",)]
        with (
            patch("backend.kafka.anomaly_syncer.get_cursor") as mock_get_cursor,
            patch(
                "backend.kafka.anomaly_syncer.get_redis_client",
                return_value=redis_client,
            ),
            patch("backend.kafka.anomaly_syncer.ChromaBuffer") as mock_cls,
        ):
            mock_get_cursor.return_value.__enter__.return_value = mock_cursor
            mock_cls.return_value = MagicMock()
            from backend.kafka.anomaly_syncer import AnomalySyncer

            yield AnomalySyncer(), mock_cls.return_value

    def test_query_excludes_null_atm_and_drops_not_in(self):
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []
        mock_cursor.description = [("id",)]
        with (
            patch("backend.kafka.anomaly_syncer.get_cursor") as mock_get_cursor,
            patch("backend.kafka.anomaly_syncer.get_redis_client", return_value=None),
            patch("backend.kafka.anomaly_syncer.ChromaBuffer"),
        ):
            mock_get_cursor.return_value.__enter__.return_value = mock_cursor
            from backend.kafka.anomaly_syncer import AnomalySyncer

            syncer = AnomalySyncer()
            syncer._get_unsynced_anomalies()

        sql = mock_cursor.execute.call_args[0][0]
        assert "atm_id IS NOT NULL" in sql
        assert "NOT IN" not in sql

    def test_restart_reuses_redis_state_no_duplicate_resync(self):
        fake_redis = _FakeRedis()
        rows = [_row(1), _row(2)]

        with self._syncer_with_rows(fake_redis, rows) as (syncer_a, buffer_a):
            result_a = syncer_a.sync_once()
        assert result_a["synced"] == 2
        assert buffer_a.add_event.call_count == 2

        # Fresh process: empty in-memory set, but Redis still has the keys.
        with self._syncer_with_rows(fake_redis, rows) as (syncer_b, buffer_b):
            result_b = syncer_b.sync_once()
        assert result_b["synced"] == 0
        buffer_b.add_event.assert_not_called()

    def test_redis_unavailable_falls_back_to_in_memory(self):
        rows = [_row(1)]
        with self._syncer_with_rows(None, rows) as (syncer, buffer):
            assert syncer.sync_once()["synced"] == 1
            # Same process, Redis still down: in-memory set prevents re-sync.
            assert syncer.sync_once()["synced"] == 0
        assert buffer.add_event.call_count == 1

    def test_sync_state_keys_use_retention_sized_ttl(self):
        from backend.kafka.anomaly_syncer import SYNC_STATE_TTL_SECONDS

        fake_redis = _FakeRedis()
        with self._syncer_with_rows(fake_redis, [_row(9)]) as (syncer, _buffer):
            syncer.sync_once()
        assert "anomaly:synced:9" in fake_redis.keys
        # 7 days matches the default anomaly retention (retention_config).
        assert SYNC_STATE_TTL_SECONDS == 7 * 24 * 3600

    def test_failed_sync_not_marked(self):
        fake_redis = _FakeRedis()
        with self._syncer_with_rows(fake_redis, [_row(1)]) as (syncer, buffer):
            buffer.add_event.side_effect = Exception("Chroma error")
            result = syncer.sync_once()
        assert result["synced"] == 0
        assert fake_redis.keys == set()
        assert syncer._synced_ids == set()
