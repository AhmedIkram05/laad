"""Unit tests for generator emitters (Kafka producer-based).

All emitters now accept (producer, timestamp) instead of (cursor, timestamp).
Tests mock the Kafka producer to verify correct topic routing and field structure.
"""
from __future__ import annotations
import pytest
from unittest.mock import MagicMock, patch, ANY
from datetime import datetime, timezone

from backend.generator.emitters import (
    emit_atm_app_events,
    emit_hardware_events,
    emit_terminal_handler_events,
    emit_kafka_events,
    emit_kafka_metrics,
    emit_prometheus_metrics,
    emit_windows_os_metrics,
    emit_gcp_metrics,
    BASELINE_EMITTERS,
)


def _mock_producer():
    return MagicMock()


class TestEmitAtmAppEvents:
    def test_sends_event_to_atm_events_topic(self):
        mock = _mock_producer()
        t = datetime.now(timezone.utc)
        emit_atm_app_events(mock, t)
        mock.send_event.assert_called()


class TestEmitHardwareEvents:
    def test_sends_event_with_hardware_source(self):
        mock = _mock_producer()
        t = datetime.now(timezone.utc)
        emit_hardware_events(mock, t)
        if mock.send_event.called:
            call_args = mock.send_event.call_args[0][0]
            assert call_args["source"] == "HARDWARE"

    def test_probability_filter(self):
        mock = _mock_producer()
        t = datetime.now(timezone.utc)
        with patch("backend.generator.emitters.random.random", return_value=0.999):
            emit_hardware_events(mock, t)
            assert mock.send_event.call_count == 0


class TestEmitTerminalHandlerEvents:
    def test_sends_event_with_terminal_handler_source(self):
        mock = _mock_producer()
        t = datetime.now(timezone.utc)
        emit_terminal_handler_events(mock, t)
        if mock.send_event.called:
            call_args = mock.send_event.call_args[0][0]
            assert call_args["source"] == "TERMINAL_HANDLER"


class TestEmitKafkaEvents:
    def test_sends_kafka_source_event(self):
        mock = _mock_producer()
        t = datetime.now(timezone.utc)
        emit_kafka_events(mock, t)
        if mock.send_event.called:
            call_args = mock.send_event.call_args[0][0]
            assert call_args["source"] == "KAFKA"


class TestEmitKafkaMetrics:
    def test_sends_metric_to_atm_metrics_topic(self):
        mock = _mock_producer()
        t = datetime.now(timezone.utc)
        emit_kafka_metrics(mock, t)
        mock.send_metric.assert_called()

    def test_metric_has_required_fields(self):
        mock = _mock_producer()
        t = datetime.now(timezone.utc)
        emit_kafka_metrics(mock, t)
        if mock.send_metric.called:
            call_args = mock.send_metric.call_args[0][0]
            assert "entity_id" in call_args
            assert "metric_name" in call_args
            assert "metric_value" in call_args
            assert call_args["source"] == "KAFKA"


class TestEmitPrometheusMetrics:
    def test_sends_metric_with_prometheus_source(self):
        mock = _mock_producer()
        t = datetime.now(timezone.utc)
        emit_prometheus_metrics(mock, t)
        if mock.send_metric.called:
            call_args = mock.send_metric.call_args[0][0]
            assert call_args["source"] == "PROMETHEUS"


class TestEmitWindowsOsMetrics:
    def test_sends_metric_with_os_source(self):
        mock = _mock_producer()
        t = datetime.now(timezone.utc)
        emit_windows_os_metrics(mock, t)
        if mock.send_metric.called:
            call_args = mock.send_metric.call_args[0][0]
            assert call_args["source"] == "OS"


class TestEmitGcpMetrics:
    def test_sends_metric_with_cloud_source(self):
        mock = _mock_producer()
        t = datetime.now(timezone.utc)
        emit_gcp_metrics(mock, t)
        if mock.send_metric.called:
            call_args = mock.send_metric.call_args[0][0]
            assert call_args["source"] == "CLOUD"


class TestBaselineEmittersList:
    def test_all_emitters_in_baseline_list(self):
        assert emit_atm_app_events in BASELINE_EMITTERS
        assert emit_hardware_events in BASELINE_EMITTERS
        assert emit_terminal_handler_events in BASELINE_EMITTERS
        assert emit_kafka_events in BASELINE_EMITTERS
        assert emit_kafka_metrics in BASELINE_EMITTERS
        assert emit_prometheus_metrics in BASELINE_EMITTERS
        assert emit_windows_os_metrics in BASELINE_EMITTERS
        assert emit_gcp_metrics in BASELINE_EMITTERS
        assert len(BASELINE_EMITTERS) == 8

    def test_all_emitters_accept_producer_argument(self):
        mock = _mock_producer()
        t = datetime.now(timezone.utc)
        for emitter in BASELINE_EMITTERS:
            try:
                emitter(mock, t)
            except TypeError as exc:
                pytest.fail(f"{emitter.__name__} does not accept (producer, timestamp): {exc}")

    def test_no_psycopg2_import_in_emitters(self):
        import backend.generator.emitters as em
        assert not hasattr(em, "psycopg2"), "emitters.py must not import psycopg2"
        assert not hasattr(em, "insert_event"), "emitters.py must not have insert_event function"
        assert not hasattr(em, "insert_metric"), "emitters.py must not have insert_metric function"