"""Unit tests for Kafka producer."""

from __future__ import annotations
from unittest.mock import MagicMock, patch
import sys
from datetime import datetime, timezone

_kafka_mock = MagicMock()
sys.modules["kafka"] = _kafka_mock
sys.modules["kafka.errors"] = _kafka_mock.errors

from backend.kafka.producer import (  # noqa: E402
    ATMProducer,
    get_producer,
    TOPIC_EVENTS,
    TOPIC_METRICS,
)


class TestATMProducer:
    def test_send_event_adds_message_id(self):
        with patch("backend.kafka.producer.KafkaProducer") as mock_klass:
            mock_instance = MagicMock()
            mock_klass.return_value = mock_instance

            producer = ATMProducer()
            event = {
                "timestamp": datetime.now(timezone.utc),
                "source": "ATM_APP",
                "atm_id": "ATM-GB-0001",
                "event_type": "ACTIVITY",
                "severity": "INFO",
                "message": "Test",
                "payload": {},
            }
            producer.send_event(event)

            sent = mock_instance.send.call_args
            assert sent is not None
            msg_value = sent.kwargs["value"] if sent.kwargs else sent[1].get("value")
            assert "message_id" in msg_value
            assert msg_value["source"] == "ATM_APP"

    def test_send_event_sends_to_topic_events(self):
        with patch("backend.kafka.producer.KafkaProducer") as mock_klass:
            mock_instance = MagicMock()
            mock_klass.return_value = mock_instance

            producer = ATMProducer()
            producer.send_event(
                {
                    "source": "ATM_APP",
                    "timestamp": "2026-05-12T10:00:00Z",
                    "severity": "INFO",
                    "payload": {},
                }
            )

            args = mock_instance.send.call_args[0]
            assert args[0] == TOPIC_EVENTS

    def test_send_metric_sends_to_topic_metrics(self):
        with patch("backend.kafka.producer.KafkaProducer") as mock_klass:
            mock_instance = MagicMock()
            mock_klass.return_value = mock_instance

            producer = ATMProducer()
            producer.send_metric(
                {
                    "timestamp": "2026-05-12T10:00:00Z",
                    "source": "PROMETHEUS",
                    "entity_id": "pod-0",
                    "metric_name": "cpu",
                    "metric_value": 0.5,
                    "payload": {},
                }
            )

            args = mock_instance.send.call_args[0]
            assert args[0] == TOPIC_METRICS

    def test_send_event_timestamp_datetime_converted_to_iso(self):
        with patch("backend.kafka.producer.KafkaProducer") as mock_klass:
            mock_instance = MagicMock()
            mock_klass.return_value = mock_instance

            producer = ATMProducer()
            dt = datetime(2026, 5, 12, 10, 0, 0, tzinfo=timezone.utc)
            producer.send_event(
                {
                    "timestamp": dt,
                    "source": "ATM_APP",
                    "severity": "INFO",
                    "payload": {},
                }
            )

            msg_value = mock_instance.send.call_args[1]["value"]
            assert "2026-05-12" in msg_value["timestamp"]

    def test_flush_calls_producer_flush(self):
        with patch("backend.kafka.producer.KafkaProducer") as mock_klass:
            mock_instance = MagicMock()
            mock_klass.return_value = mock_instance

            producer = ATMProducer()
            producer.flush()
            assert mock_instance.flush.called

    def test_close_flushes_and_closes(self):
        with patch("backend.kafka.producer.KafkaProducer") as mock_klass:
            mock_instance = MagicMock()
            mock_klass.return_value = mock_instance

            producer = ATMProducer()
            producer.close()
            mock_instance.flush.assert_called_once()
            mock_instance.close.assert_called_once()

    def test_error_handling_on_send(self):
        with patch("backend.kafka.producer.KafkaProducer") as mock_klass:
            from kafka.errors import KafkaError

            mock_instance = MagicMock()
            mock_instance.send.side_effect = KafkaError("boom")
            mock_klass.return_value = mock_instance

            producer = ATMProducer()
            producer.send_event(
                {
                    "source": "ATM_APP",
                    "timestamp": "2026-05-12T10:00:00Z",
                    "severity": "INFO",
                    "payload": {},
                }
            )


class TestGetProducer:
    def test_singleton(self):
        import backend.kafka.producer as mod

        old = getattr(mod, "_producer_instance", None)
        mod._producer_instance = None
        try:
            p1 = get_producer()
            p2 = get_producer()
            assert p1 is p2
        finally:
            mod._producer_instance = old
