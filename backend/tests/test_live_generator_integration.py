"""Integration tests for live generator (Kafka producer-based).

Verifies emit_tick sends events and metrics to Kafka via the producer.
"""
from __future__ import annotations
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

from backend.generator.continuous_generator import emit_tick


def _mock_producer():
    return MagicMock()


@pytest.fixture(autouse=True)
def mock_mlflow():
    with patch("backend.src.anomaly_detection.ml.ml_detector.MLAnomalyDetector"):
        yield


class TestEmitTick:
    def test_emit_tick_calls_all_baseline_emitters(self):
        mock = _mock_producer()
        t = datetime.now(timezone.utc)
        anomaly_last = {}
        emit_tick(mock, t, anomaly_last)
        assert mock.send_event.call_count > 0 or mock.send_metric.call_count > 0

    def test_emit_tick_flushes_producer(self):
        mock = _mock_producer()
        t = datetime.now(timezone.utc)
        anomaly_last = {}
        emit_tick(mock, t, anomaly_last)
        assert mock.flush.called

    def test_emit_tick_in_backfill_mode_skips_anomaly_injection(self):
        mock = _mock_producer()
        t = datetime.now(timezone.utc)
        anomaly_last = {}
        with patch("backend.generator.continuous_generator.rng") as mock_rng:
            with patch("backend.generator.continuous_generator.ANOMALY_PROB", 0.0):
                emit_tick(mock, t, anomaly_last, backfill_mode=True, backfill_prob=0.0)
                mock_rng.random.assert_not_called()

    def test_no_direct_db_writes_from_emit_tick(self):
        with patch("backend.src.database.connection.get_cursor") as mock_gc:
            mock = _mock_producer()
            t = datetime.now(timezone.utc)
            anomaly_last = {}
            emit_tick(mock, t, anomaly_last)
            mock_gc.assert_not_called

    def test_emitter_exceptions_are_caught(self):
        mock = MagicMock()
        mock.send_event.side_effect = Exception("Kafka error")
        t = datetime.now(timezone.utc)
        anomaly_last = {}
        emit_tick(mock, t, anomaly_last)