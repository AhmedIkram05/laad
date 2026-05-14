"""Unit tests for Kafka consumer."""
from __future__ import annotations
import pytest
import signal
import threading
import time
from unittest.mock import MagicMock, patch, Mock

import sys

_kafka_mock = MagicMock()
sys.modules["kafka"] = _kafka_mock
sys.modules["kafka.errors"] = _kafka_mock.errors

from backend.kafka.consumer import (
    _deserialise,
    _trigger_anomaly_detection,
    _handle_sigterm,
    run_consumer,
    TOPIC_EVENTS,
    TOPIC_METRICS,
)
from backend.kafka import consumer as c


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
    @patch("backend.kafka.consumer.MLAnomalyDetector")
    def test_calls_detect_and_save(self, mock_detector_class):
        mock_instance = MagicMock()
        mock_instance.detect_and_save.return_value = 3
        mock_detector_class.return_value = mock_instance

        _trigger_anomaly_detection()

        mock_instance.detect_and_save.assert_called_once()

    @patch("backend.kafka.consumer._cached_detector", None)
    @patch("backend.kafka.consumer.MLAnomalyDetector")
    def test_logs_when_anomalies_found(self, mock_detector_class):
        mock_instance = MagicMock()
        mock_instance.detect_and_save.return_value = 5
        mock_detector_class.return_value = mock_instance

        with patch("backend.kafka.consumer.log") as mock_log:
            _trigger_anomaly_detection()
            mock_log.info.assert_called()
            assert "5" in mock_log.info.call_args[0][0]

    @patch("backend.kafka.consumer._cached_detector", None)
    @patch("backend.kafka.consumer.MLAnomalyDetector")
    def test_handles_import_error_gracefully(self, mock_detector_class):
        mock_detector_class.side_effect = ImportError("module not found")

        with patch("backend.kafka.consumer.log") as mock_log:
            _trigger_anomaly_detection()
            mock_log.warning.assert_called()

    @patch("backend.kafka.consumer._cached_detector", None)
    @patch("backend.kafka.consumer.MLAnomalyDetector")
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


class TestRunConsumerRouting:
    @patch("backend.kafka.consumer.ChromaBuffer")
    @patch("backend.kafka.consumer.KafkaConsumer")
    @patch("backend.kafka.consumer.handle_event")
    @patch("backend.kafka.consumer.handle_metric")
    @patch("backend.kafka.consumer.route_raw_ingestion_errors")
    def test_events_routed_to_event_handler(
        self, mock_route_errors, mock_handle_event, mock_handle_metric, mock_kafka_class, mock_chroma_class
    ):
        mock_cur = MagicMock()
        mock_cur.execute.side_effect = Exception("done")
        mock_cur.__enter__ = MagicMock(return_value=mock_cur)
        mock_cur.__exit__ = MagicMock(return_value=False)

        mock_record = MagicMock()
        mock_record.value = b'{"message_id": "m1", "timestamp": "2026-05-12T10:00:00Z", "source": "ATM_APP", "severity": "INFO"}'

        mock_tp = MagicMock()
        mock_tp.topic = TOPIC_EVENTS

        mock_poll_result = {mock_tp: [mock_record]}

        mock_consumer = MagicMock()
        mock_consumer.poll.side_effect = [mock_poll_result, KeyboardInterrupt("stop")]
        mock_kafka_class.return_value = mock_consumer

        mock_buffer = MagicMock()
        mock_chroma_class.return_value = mock_buffer

        with pytest.raises(KeyboardInterrupt):
            run_consumer()

        mock_handle_event.assert_called_once()
        mock_handle_metric.assert_not_called()

    @patch("backend.kafka.consumer.ChromaBuffer")
    @patch("backend.kafka.consumer.KafkaConsumer")
    @patch("backend.kafka.consumer.handle_event")
    @patch("backend.kafka.consumer.handle_metric")
    @patch("backend.kafka.consumer.route_raw_ingestion_errors")
    def test_metrics_routed_to_metric_handler(
        self, mock_route_errors, mock_handle_event, mock_handle_metric, mock_kafka_class, mock_chroma_class
    ):
        mock_cur = MagicMock()
        mock_cur.execute.side_effect = Exception("done")
        mock_cur.__enter__ = MagicMock(return_value=mock_cur)
        mock_cur.__exit__ = MagicMock(return_value=False)

        mock_record = MagicMock()
        mock_record.value = b'{"message_id": "m2", "timestamp": "2026-05-12T10:00:00Z", "source": "PROMETHEUS", "entity_id": "pod-0", "metric_name": "cpu", "metric_value": 0.5}'

        mock_tp = MagicMock()
        mock_tp.topic = TOPIC_METRICS

        mock_poll_result = {mock_tp: [mock_record]}

        mock_consumer = MagicMock()
        mock_consumer.poll.side_effect = [mock_poll_result, KeyboardInterrupt("stop")]
        mock_kafka_class.return_value = mock_consumer

        mock_chroma_class.return_value = MagicMock()

        with pytest.raises(KeyboardInterrupt):
            run_consumer()

        mock_handle_metric.assert_called_once()
        mock_handle_event.assert_not_called()

    @patch("backend.kafka.consumer.ChromaBuffer")
    @patch("backend.kafka.consumer.KafkaConsumer")
    @patch("backend.kafka.consumer.handle_event")
    @patch("backend.kafka.consumer.handle_metric")
    @patch("backend.kafka.consumer.Deduplicator")
    @patch("backend.kafka.consumer.route_raw_ingestion_errors")
    def test_duplicate_message_skipped(
        self, mock_route_errors, mock_dedup_class, mock_handle_event, mock_handle_metric, mock_kafka_class, mock_chroma_class
    ):
        mock_dedup = MagicMock()
        mock_dedup.is_duplicate.return_value = True
        mock_dedup_class.return_value = mock_dedup

        mock_record = MagicMock()
        mock_record.value = b'{"message_id": "dup-1", "timestamp": "2026-05-12T10:00:00Z", "source": "ATM_APP", "severity": "INFO"}'

        mock_tp = MagicMock()
        mock_tp.topic = TOPIC_EVENTS

        mock_poll_result = {mock_tp: [mock_record]}

        mock_consumer = MagicMock()
        mock_consumer.poll.side_effect = [mock_poll_result, KeyboardInterrupt("stop")]
        mock_kafka_class.return_value = mock_consumer

        mock_chroma_class.return_value = MagicMock()

        with pytest.raises(KeyboardInterrupt):
            run_consumer()

        mock_handle_event.assert_not_called()
        mock_dedup.is_duplicate.assert_called_once_with("dup-1")

    @patch("backend.kafka.consumer.ChromaBuffer")
    @patch("backend.kafka.consumer.KafkaConsumer")
    @patch("backend.kafka.consumer.handle_event")
    @patch("backend.kafka.consumer.handle_metric")
    @patch("backend.kafka.consumer.Deduplicator")
    @patch("backend.kafka.consumer.route_raw_ingestion_errors")
    def test_manual_commit_after_batch(
        self, mock_route_errors, mock_dedup_class, mock_handle_event, mock_handle_metric, mock_kafka_class, mock_chroma_class
    ):
        mock_dedup_class.return_value = MagicMock()

        mock_record = MagicMock()
        mock_record.value = b'{"message_id": "c1", "timestamp": "2026-05-12T10:00:00Z", "source": "ATM_APP", "severity": "INFO"}'

        mock_tp = MagicMock()
        mock_tp.topic = TOPIC_EVENTS

        mock_consumer = MagicMock()
        mock_consumer.poll.side_effect = [
            {mock_tp: [mock_record]},
            KeyboardInterrupt("stop"),
        ]
        mock_kafka_class.return_value = mock_consumer

        mock_chroma_class.return_value = MagicMock()

        with pytest.raises(KeyboardInterrupt):
            run_consumer()

        mock_consumer.commit.assert_called_once()

    @patch("backend.kafka.consumer.ChromaBuffer")
    @patch("backend.kafka.consumer.KafkaConsumer")
    @patch("backend.kafka.consumer.handle_event")
    @patch("backend.kafka.consumer.handle_metric")
    @patch("backend.kafka.consumer.Deduplicator")
    @patch("backend.kafka.consumer.route_raw_ingestion_errors")
    @patch("backend.kafka.consumer.time.monotonic")
    @patch("backend.kafka.consumer._trigger_anomaly_detection")
    def test_rate_limiting_of_anomaly_trigger(
        self, mock_trigger, mock_monotonic, mock_dedup_class,
        mock_route_errors, mock_handle_event, mock_handle_metric, mock_kafka_class, mock_chroma_class
    ):
        mock_dedup_class.return_value = MagicMock()

        mock_record = MagicMock()
        mock_record.value = b'{"message_id": "r1", "timestamp": "2026-05-12T10:00:00Z", "source": "ATM_APP", "severity": "INFO"}'

        mock_tp = MagicMock()
        mock_tp.topic = TOPIC_EVENTS

        mock_consumer = MagicMock()
        mock_consumer.poll.side_effect = [
            {mock_tp: [mock_record]},
            {mock_tp: [mock_record]},
            KeyboardInterrupt("stop"),
        ]
        mock_kafka_class.return_value = mock_consumer

        mock_chroma_class.return_value = MagicMock()

        mock_monotonic.side_effect = [0.0, 0.0, 35.0]

        with pytest.raises(KeyboardInterrupt):
            run_consumer()

        assert mock_trigger.call_count == 1

    @patch("backend.kafka.consumer.ChromaBuffer")
    @patch("backend.kafka.consumer.KafkaConsumer")
    @patch("backend.kafka.consumer.handle_event")
    @patch("backend.kafka.consumer.handle_metric")
    @patch("backend.kafka.consumer.Deduplicator")
    @patch("backend.kafka.consumer.route_raw_ingestion_errors")
    @patch("backend.kafka.consumer.time.monotonic")
    @patch("backend.kafka.consumer.log")
    def test_stats_logged_at_500(
        self, mock_log, mock_monotonic, mock_dedup_class,
        mock_route_errors, mock_handle_event, mock_handle_metric, mock_kafka_class, mock_chroma_class
    ):
        mock_dedup_class.return_value = MagicMock()

        mock_record = MagicMock()
        mock_record.value = b'{"message_id": "s1", "timestamp": "2026-05-12T10:00:00Z", "source": "ATM_APP", "severity": "INFO"}'

        mock_tp = MagicMock()
        mock_tp.topic = TOPIC_EVENTS

        call_count = [0]

        def poll_side_effect():
            call_count[0] += 1
            if call_count[0] < 2:
                return {mock_tp: [mock_record]}
            raise KeyboardInterrupt("stop")

        mock_consumer = MagicMock()
        mock_consumer.poll.side_effect = poll_side_effect
        mock_kafka_class.return_value = mock_consumer

        mock_chroma_class.return_value = MagicMock()

        with pytest.raises(KeyboardInterrupt):
            run_consumer()

        info_calls = [c for c in mock_log.info.call_args_list if "messages" in str(c)]
        assert len(info_calls) >= 1

    @patch("backend.kafka.consumer.ChromaBuffer")
    @patch("backend.kafka.consumer.KafkaConsumer")
    @patch("backend.kafka.consumer.handle_event")
    @patch("backend.kafka.consumer.handle_metric")
    @patch("backend.kafka.consumer.Deduplicator")
    @patch("backend.kafka.consumer.route_raw_ingestion_errors")
    @patch("backend.kafka.consumer.log")
    def test_unknown_topic_writes_false(
        self, mock_log, mock_dedup_class, mock_route_errors,
        mock_handle_event, mock_handle_metric, mock_kafka_class, mock_chroma_class
    ):
        mock_dedup_class.return_value = MagicMock()

        mock_record = MagicMock()
        mock_record.value = b'{"message_id": "u1", "timestamp": "2026-05-12T10:00:00Z", "source": "ATM_APP", "severity": "INFO"}'

        mock_tp = MagicMock()
        mock_tp.topic = "unknown-topic"

        mock_consumer = MagicMock()
        mock_consumer.poll.side_effect = [{mock_tp: [mock_record]}, KeyboardInterrupt("stop")]
        mock_kafka_class.return_value = mock_consumer

        mock_chroma_class.return_value = MagicMock()

        with pytest.raises(KeyboardInterrupt):
            run_consumer()

        mock_handle_event.assert_not_called()
        mock_handle_metric.assert_not_called()
        mock_log.warning.assert_called()