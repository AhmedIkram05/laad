"""Unit tests for Kafka consumer."""

from __future__ import annotations
from unittest.mock import MagicMock, patch
from itertools import cycle

import sys

import pytest

pytestmark = pytest.mark.kafka

_kafka_mock = MagicMock()
sys.modules["kafka"] = _kafka_mock
sys.modules["kafka.errors"] = _kafka_mock.errors

from backend.kafka.consumer import (  # noqa: E402
    _deserialise,
    _trigger_anomaly_detection,
    _handle_sigterm,
    run_consumer,
    TOPIC_EVENTS,
    TOPIC_METRICS,
)
from backend.kafka import consumer as c  # noqa: E402
from backend.kafka.handlers import event_handler, metric_handler  # noqa: E402


class TestDeserialise:
    def test_valid_json(self):
        raw = b'{"message_id": "m1", "timestamp": "2026-05-12T10:00:00Z", "source": "ATM_APP", "severity": "INFO"}'
        result = _deserialise(raw)
        assert result["message_id"] == "m1"
        assert result["source"] == "ATM_APP"

    def test_invalid_json_returns_none(self):
        raw = b"not valid json {"
        result = _deserialise(raw)
        assert result is None

    def test_unicode_decode_error_returns_none(self):
        raw = b"\xff\xfe invalid"
        result = _deserialise(raw)
        assert result is None

    def test_empty_bytes(self):
        raw = b""
        result = _deserialise(raw)
        assert result is None


class TestTriggerAnomalyDetection:
    @patch("backend.kafka.consumer._cached_detector", None)
    @patch("backend.src.anomaly_detection.ml.ml_detector.MLAnomalyDetector")
    def test_calls_detect_and_save(self, mock_detector_class):
        mock_instance = MagicMock()
        mock_instance.detect_and_save.return_value = 3
        mock_detector_class.return_value = mock_instance

        _trigger_anomaly_detection()

        mock_instance.detect_and_save.assert_called_once()

    @patch("backend.kafka.consumer._cached_detector", None)
    @patch("backend.src.anomaly_detection.ml.ml_detector.MLAnomalyDetector")
    def test_logs_when_anomalies_found(self, mock_detector_class):
        mock_instance = MagicMock()
        mock_instance.detect_and_save.return_value = 5
        mock_detector_class.return_value = mock_instance

        with patch("backend.kafka.consumer.log") as mock_log:
            _trigger_anomaly_detection()
            mock_log.info.assert_called()
            assert any("5" in str(a) for a in mock_log.info.call_args_list)

    @patch("backend.kafka.consumer._cached_detector", None)
    @patch("backend.src.anomaly_detection.ml.ml_detector.MLAnomalyDetector")
    def test_handles_import_error_gracefully(self, mock_detector_class):
        mock_detector_class.side_effect = ImportError("module not found")

        with patch("backend.kafka.consumer.log") as mock_log:
            _trigger_anomaly_detection()
            mock_log.warning.assert_called()

    @patch("backend.kafka.consumer._cached_detector", None)
    @patch("backend.src.anomaly_detection.ml.ml_detector.MLAnomalyDetector")
    def test_handles_runtime_error_gracefully(self, mock_detector_class):
        mock_instance = MagicMock()
        mock_instance.detect_and_save.side_effect = Exception("Detection failed")
        mock_detector_class.return_value = mock_instance

        with patch("backend.kafka.consumer.log") as mock_log:
            _trigger_anomaly_detection()
            mock_log.warning.assert_called()


class TestHandleSigterm:
    def test_sets_running_false(self):
        original = c._running
        c._running = True
        try:
            _handle_sigterm(None, None)
            assert c._running is False
        finally:
            c._running = original


class _PollOnceThenStop(Exception):
    pass


class TestRunConsumerRouting:
    def _make_poll(self, mock_tp, mock_record, times=1):
        """Returns a poll function that yields {mock_tp: [mock_record]} for `times` calls then raises."""
        call_idx = [0]

        def poll(*args, **kwargs):
            if call_idx[0] < times:
                call_idx[0] += 1
                return {mock_tp: [mock_record]}
            raise _PollOnceThenStop()

        return poll

    def test_events_routed_to_event_handler(self):
        mock_record = MagicMock()
        mock_record.value = b'{"message_id": "m1", "timestamp": "2026-05-12T10:00:00Z", "source": "ATM_APP", "severity": "INFO"}'
        mock_tp = MagicMock()
        mock_tp.topic = TOPIC_EVENTS

        handle_event = MagicMock(return_value=True)
        handle_metric = MagicMock(return_value=True)
        mock_consumer = MagicMock()
        mock_consumer.poll = self._make_poll(mock_tp, mock_record)
        mock_consumer.commit = MagicMock()
        mock_consumer.close = MagicMock()
        mock_dedup = MagicMock()

        with (
            patch(
                "backend.kafka.handlers.event_handler.handle_event",
                side_effect=handle_event,
            ),
            patch(
                "backend.kafka.handlers.metric_handler.handle_metric",
                side_effect=handle_metric,
            ),
            patch("backend.kafka.consumer.KafkaConsumer", return_value=mock_consumer),
            patch("backend.kafka.consumer.Deduplicator", return_value=mock_dedup),
            patch("backend.kafka.consumer.ChromaBuffer", return_value=MagicMock()),
            patch("backend.kafka.consumer.route_raw_ingestion_errors"),
            patch(
                "backend.kafka.consumer.time.monotonic", side_effect=cycle([0.0, 1.0])
            ),
        ):
            try:
                run_consumer()
            except _PollOnceThenStop:
                pass

        handle_event.assert_called_once()
        handle_metric.assert_not_called()

    def test_metrics_routed_to_metric_handler(self):
        mock_record = MagicMock()
        mock_record.value = b'{"message_id": "m2", "timestamp": "2026-05-12T10:00:00Z", "source": "PROMETHEUS", "entity_id": "pod-0", "metric_name": "cpu", "metric_value": 0.5}'
        mock_tp = MagicMock()
        mock_tp.topic = TOPIC_METRICS

        handle_event = MagicMock(return_value=True)
        handle_metric = MagicMock(return_value=True)
        mock_consumer = MagicMock()
        mock_consumer.poll = self._make_poll(mock_tp, mock_record)
        mock_consumer.commit = MagicMock()
        mock_consumer.close = MagicMock()
        mock_dedup = MagicMock()

        with (
            patch(
                "backend.kafka.handlers.event_handler.handle_event",
                side_effect=handle_event,
            ),
            patch(
                "backend.kafka.handlers.metric_handler.handle_metric",
                side_effect=handle_metric,
            ),
            patch("backend.kafka.consumer.KafkaConsumer", return_value=mock_consumer),
            patch("backend.kafka.consumer.Deduplicator", return_value=mock_dedup),
            patch("backend.kafka.consumer.ChromaBuffer", return_value=MagicMock()),
            patch("backend.kafka.consumer.route_raw_ingestion_errors"),
            patch(
                "backend.kafka.consumer.time.monotonic", side_effect=cycle([0.0, 1.0])
            ),
        ):
            try:
                run_consumer()
            except _PollOnceThenStop:
                pass

        handle_metric.assert_called_once()
        handle_event.assert_not_called()

    def test_duplicate_message_skipped(self):
        mock_record = MagicMock()
        mock_record.value = b'{"message_id": "dup-1", "timestamp": "2026-05-12T10:00:00Z", "source": "ATM_APP", "severity": "INFO"}'
        mock_tp = MagicMock()
        mock_tp.topic = TOPIC_EVENTS

        handle_event = MagicMock(return_value=True)
        handle_metric = MagicMock(return_value=True)
        mock_dedup = MagicMock()
        mock_dedup.is_duplicate.return_value = True
        mock_consumer = MagicMock()
        mock_consumer.poll = self._make_poll(mock_tp, mock_record)
        mock_consumer.commit = MagicMock()
        mock_consumer.close = MagicMock()

        with (
            patch("backend.kafka.consumer.KafkaConsumer", return_value=mock_consumer),
            patch("backend.kafka.consumer.Deduplicator", return_value=mock_dedup),
            patch("backend.kafka.consumer.ChromaBuffer", return_value=MagicMock()),
            patch.object(event_handler, "handle_event", side_effect=handle_event),
            patch.object(metric_handler, "handle_metric", side_effect=handle_metric),
            patch("backend.kafka.consumer.route_raw_ingestion_errors"),
            patch(
                "backend.kafka.consumer.time.monotonic", side_effect=cycle([0.0, 1.0])
            ),
        ):
            try:
                run_consumer()
            except _PollOnceThenStop:
                pass

        handle_event.assert_not_called()
        mock_dedup.is_duplicate.assert_called_once_with("dup-1")

    def test_manual_commit_after_batch(self):
        mock_record = MagicMock()
        mock_record.value = b'{"message_id": "c1", "timestamp": "2026-05-12T10:00:00Z", "source": "ATM_APP", "severity": "INFO"}'
        mock_tp = MagicMock()
        mock_tp.topic = TOPIC_EVENTS

        handle_event = MagicMock(return_value=True)
        handle_metric = MagicMock(return_value=True)
        mock_consumer = MagicMock()
        mock_consumer.poll = self._make_poll(mock_tp, mock_record)
        mock_consumer.commit = MagicMock()
        mock_consumer.close = MagicMock()
        mock_dedup = MagicMock()

        with (
            patch("backend.kafka.consumer.KafkaConsumer", return_value=mock_consumer),
            patch("backend.kafka.consumer.Deduplicator", return_value=mock_dedup),
            patch("backend.kafka.consumer.ChromaBuffer", return_value=MagicMock()),
            patch.object(event_handler, "handle_event", side_effect=handle_event),
            patch.object(metric_handler, "handle_metric", side_effect=handle_metric),
            patch("backend.kafka.consumer.route_raw_ingestion_errors"),
            patch(
                "backend.kafka.consumer.time.monotonic", side_effect=cycle([0.0, 1.0])
            ),
        ):
            try:
                run_consumer()
            except _PollOnceThenStop:
                pass

        mock_consumer.commit.assert_called()

    def test_rate_limiting_of_anomaly_trigger(self):
        mock_record = MagicMock()
        mock_record.value = b'{"message_id": "r1", "timestamp": "2026-05-12T10:00:00Z", "source": "ATM_APP", "severity": "INFO"}'
        mock_tp = MagicMock()
        mock_tp.topic = TOPIC_EVENTS

        handle_event = MagicMock(return_value=True)
        handle_metric = MagicMock(return_value=True)
        mock_consumer = MagicMock()
        mock_consumer.poll = self._make_poll(mock_tp, mock_record, times=2)
        mock_consumer.commit = MagicMock()
        mock_consumer.close = MagicMock()
        mock_dedup = MagicMock()
        mock_dedup.is_duplicate.return_value = False
        mock_trigger = MagicMock()

        with (
            patch("backend.kafka.consumer.KafkaConsumer", return_value=mock_consumer),
            patch("backend.kafka.consumer.Deduplicator", return_value=mock_dedup),
            patch("backend.kafka.consumer.ChromaBuffer", return_value=MagicMock()),
            patch.object(event_handler, "handle_event", side_effect=handle_event),
            patch.object(metric_handler, "handle_metric", side_effect=handle_metric),
            patch("backend.kafka.consumer.route_raw_ingestion_errors"),
            patch(
                "backend.kafka.consumer._trigger_anomaly_detection",
                side_effect=mock_trigger,
            ),
            patch("backend.kafka.consumer.time.monotonic", side_effect=[0.0, 35.0]),
        ):
            try:
                run_consumer()
            except _PollOnceThenStop:
                pass

        assert mock_trigger.call_count == 1

    def test_stats_logged_at_500(self):
        mock_records = []
        for idx in range(500):
            mock_record = MagicMock()
            mock_record.value = (
                f'{{"message_id": "s{idx}", "timestamp": "2026-05-12T10:00:00Z", '
                f'"source": "ATM_APP", "severity": "INFO"}}'
            ).encode("utf-8")
            mock_records.append(mock_record)
        mock_tp = MagicMock()
        mock_tp.topic = TOPIC_EVENTS

        call_count = [0]

        def poll(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return {mock_tp: mock_records}
            raise _PollOnceThenStop()

        handle_event = MagicMock(return_value=True)
        handle_metric = MagicMock(return_value=True)
        mock_consumer = MagicMock()
        mock_consumer.poll = poll
        mock_consumer.commit = MagicMock()
        mock_consumer.close = MagicMock()
        mock_dedup = MagicMock()
        mock_dedup.is_duplicate.return_value = False
        mock_log = MagicMock()

        with (
            patch("backend.kafka.consumer.KafkaConsumer", return_value=mock_consumer),
            patch("backend.kafka.consumer.Deduplicator", return_value=mock_dedup),
            patch("backend.kafka.consumer.ChromaBuffer", return_value=MagicMock()),
            patch.object(event_handler, "handle_event", side_effect=handle_event),
            patch.object(metric_handler, "handle_metric", side_effect=handle_metric),
            patch("backend.kafka.consumer.route_raw_ingestion_errors"),
            patch("backend.kafka.consumer.log", new=mock_log),
            patch("backend.kafka.consumer.time.monotonic", return_value=0.0),
        ):
            try:
                run_consumer()
            except _PollOnceThenStop:
                pass

        info_calls = [
            call for call in mock_log.info.call_args_list if "messages" in str(call)
        ]
        assert len(info_calls) >= 1

    def test_unknown_topic_writes_false(self):
        mock_record = MagicMock()
        mock_record.value = b'{"message_id": "u1", "timestamp": "2026-05-12T10:00:00Z", "source": "ATM_APP", "severity": "INFO"}'
        mock_tp = MagicMock()
        mock_tp.topic = "unknown-topic"

        handle_event = MagicMock(return_value=True)
        handle_metric = MagicMock(return_value=True)
        mock_consumer = MagicMock()
        mock_consumer.poll = self._make_poll(mock_tp, mock_record)
        mock_consumer.commit = MagicMock()
        mock_consumer.close = MagicMock()
        mock_dedup = MagicMock()
        mock_dedup.is_duplicate.return_value = False
        mock_log = MagicMock()

        with (
            patch("backend.kafka.consumer.KafkaConsumer", return_value=mock_consumer),
            patch("backend.kafka.consumer.Deduplicator", return_value=mock_dedup),
            patch("backend.kafka.consumer.ChromaBuffer", return_value=MagicMock()),
            patch.object(event_handler, "handle_event", side_effect=handle_event),
            patch.object(metric_handler, "handle_metric", side_effect=handle_metric),
            patch("backend.kafka.consumer.route_raw_ingestion_errors"),
            patch("backend.kafka.consumer.log", new=mock_log),
            patch(
                "backend.kafka.consumer.time.monotonic", side_effect=cycle([0.0, 1.0])
            ),
        ):
            try:
                run_consumer()
            except _PollOnceThenStop:
                pass

        handle_event.assert_not_called()
        handle_metric.assert_not_called()
        mock_log.warning.assert_called()
