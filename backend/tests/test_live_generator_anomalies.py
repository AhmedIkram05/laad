"""Unit tests for anomaly injectors (Kafka producer-based).

All injectors now accept (producer, timestamp) instead of (cursor, timestamp).
Anomaly tag preservation is verified for A1-A7. A3 and A6 use state-based
progressive emission — one message per call, tracked across calls.
"""
from __future__ import annotations
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

from backend.generator.anomaly_injectors import (
    inject_a1, inject_a2, inject_a3, inject_a4, inject_a5, inject_a6, inject_a7,
    ANOMALY_REGISTRY,
)


def _mock_producer():
    return MagicMock()


@pytest.fixture(autouse=True)
def reset_anomaly_state(monkeypatch):
    """Clears progressive injector state between tests."""
    from backend.generator import anomaly_injectors as ai
    monkeypatch.setattr(ai, "_anomaly_state", {})


class TestInjectA1:
    def test_sends_variable_event_messages(self):
        mock = _mock_producer()
        t = datetime.now(timezone.utc)
        inject_a1(mock, t)
        # A1 now sends 2-4 messages (always 2 core + up to 2 optional)
        assert 2 <= mock.send_event.call_count <= 4

    def test_network_disconnect_event_present(self):
        mock = _mock_producer()
        t = datetime.now(timezone.utc)
        inject_a1(mock, t)
        calls = mock.send_event.call_args_list
        payloads = [c[0][0]["payload"] for c in calls]
        assert any(p.get("_anomaly_tag") == "A1" for p in payloads)

    def test_all_messages_share_correlation_id(self):
        mock = _mock_producer()
        t = datetime.now(timezone.utc)
        inject_a1(mock, t)
        calls = mock.send_event.call_args_list
        corr_ids = [c[0][0]["correlation_id"] for c in calls]
        assert len(set(corr_ids)) == 1

    def test_sources_include_atm_app_and_optionally_others(self):
        mock = _mock_producer()
        t = datetime.now(timezone.utc)
        inject_a1(mock, t)
        sources = {c[0][0]["source"] for c in mock.send_event.call_args_list}
        assert "ATM_APP" in sources
        # May include KAFKA and/or TERMINAL_HANDLER probabilistically


class TestInjectA2:
    def test_sends_variable_event_messages(self):
        mock = _mock_producer()
        t = datetime.now(timezone.utc)
        inject_a2(mock, t)
        # A2 now sends 2-3 messages (always CASSETTE_LOW + CASSETTE_EMPTY + optional KAFKA)
        assert 2 <= mock.send_event.call_count <= 3

    def test_anomaly_tag_present(self):
        mock = _mock_producer()
        t = datetime.now(timezone.utc)
        inject_a2(mock, t)
        payloads = [c[0][0]["payload"] for c in mock.send_event.call_args_list]
        assert any(p.get("_anomaly_tag") == "A2" for p in payloads)

    def test_sources_include_hardware_and_optionally_kafka(self):
        mock = _mock_producer()
        t = datetime.now(timezone.utc)
        inject_a2(mock, t)
        sources = {c[0][0]["source"] for c in mock.send_event.call_args_list}
        assert "HARDWARE" in sources
        # May include KAFKA probabilistically (80% chance)


class TestInjectA3:
    def test_first_call_sends_3_metric_messages(self):
        mock = _mock_producer()
        t = datetime.now(timezone.utc)
        inject_a3(mock, t)
        assert mock.send_metric.call_count == 3

    def test_anomaly_tag_present_in_all_metrics(self):
        mock = _mock_producer()
        t = datetime.now(timezone.utc)
        inject_a3(mock, t)
        for call in mock.send_metric.call_args_list:
            assert call[0][0]["payload"].get("_anomaly_tag") == "A3"

    def test_progressive_state_across_calls(self):
        mock = _mock_producer()
        t = datetime.now(timezone.utc)
        inject_a3(mock, t)
        first_count = mock.send_metric.call_count
        inject_a3(mock, t)
        assert mock.send_metric.call_count == first_count + 3

    def test_jvm_memory_metric_name_present(self):
        mock = _mock_producer()
        t = datetime.now(timezone.utc)
        inject_a3(mock, t)
        metric_names = [c[0][0]["metric_name"] for c in mock.send_metric.call_args_list]
        assert "jvm_memory_used_bytes" in metric_names

    def test_cloud_metric_included(self):
        mock = _mock_producer()
        t = datetime.now(timezone.utc)
        inject_a3(mock, t)
        sources = {c[0][0]["source"] for c in mock.send_metric.call_args_list}
        assert sources == {"PROMETHEUS", "CLOUD"}

    def test_no_oom_event_in_first_89_calls(self):
        mock = _mock_producer()
        t = datetime.now(timezone.utc)
        for _ in range(88):
            inject_a3(mock, t)
        event_count = mock.send_event.call_count
        assert event_count == 0

    def test_oom_event_on_90th_call(self):
        mock = _mock_producer()
        t = datetime.now(timezone.utc)
        inject_a3(mock, t)
        for _ in range(89):
            inject_a3(mock, t)
        assert mock.send_event.call_count == 1
        call_args = mock.send_event.call_args[0][0]
        assert call_args["payload"].get("_anomaly_tag") == "A3"
        assert call_args["event_type"] == "OOM_ERROR"

    def test_no_psycopg2_import(self):
        import backend.generator.anomaly_injectors as ai
        assert not hasattr(ai, "psycopg2"), "anomaly_injectors.py must not import psycopg2"
        assert not hasattr(ai, "insert_event"), "anomaly_injectors.py must not have insert_event function"
        assert not hasattr(ai, "insert_metric"), "anomaly_injectors.py must not have insert_metric function"


class TestInjectA4:
    def test_sends_3_event_messages(self):
        mock = _mock_producer()
        t = datetime.now(timezone.utc)
        inject_a4(mock, t)
        assert mock.send_event.call_count == 3

    def test_anomaly_tag_present(self):
        mock = _mock_producer()
        t = datetime.now(timezone.utc)
        inject_a4(mock, t)
        payloads = [c[0][0]["payload"] for c in mock.send_event.call_args_list]
        assert any(p.get("_anomaly_tag") == "A4" for p in payloads)

    def test_sources_all_terminal_handler(self):
        mock = _mock_producer()
        t = datetime.now(timezone.utc)
        inject_a4(mock, t)
        sources = {c[0][0]["source"] for c in mock.send_event.call_args_list}
        assert sources == {"TERMINAL_HANDLER"}


class TestInjectA5:
    def test_sends_variable_event_messages(self):
        mock = _mock_producer()
        t = datetime.now(timezone.utc)
        inject_a5(mock, t)
        # A5 now sends variable number of messages (8-12 METRIC + optional ATM_APP TIMEOUT + 1 STATUS)
        # Minimum: 8 METRIC + 1 STATUS = 9
        # Maximum: 12 METRIC + up to 11 ATM_APP TIMEOUT + 1 STATUS = 24
        assert mock.send_event.call_count >= 9

    def test_anomaly_tag_present_in_all(self):
        mock = _mock_producer()
        t = datetime.now(timezone.utc)
        inject_a5(mock, t)
        for call in mock.send_event.call_args_list:
            assert call[0][0]["payload"].get("_anomaly_tag") == "A5"

    def test_sources_include_kafka_and_optionally_atm_app(self):
        mock = _mock_producer()
        t = datetime.now(timezone.utc)
        inject_a5(mock, t)
        sources = {c[0][0]["source"] for c in mock.send_event.call_args_list}
        assert "KAFKA" in sources
        # May include ATM_APP probabilistically (40% chance per METRIC after first)


class TestInjectA6:
    def test_first_call_sends_1_metric_message(self):
        mock = _mock_producer()
        t = datetime.now(timezone.utc)
        inject_a6(mock, t)
        assert mock.send_metric.call_count == 1

    def test_metric_name_windows_os_snapshot(self):
        mock = _mock_producer()
        t = datetime.now(timezone.utc)
        inject_a6(mock, t)
        metric_name = mock.send_metric.call_args[0][0]["metric_name"]
        assert metric_name == "windows_os_snapshot"

    def test_source_os(self):
        mock = _mock_producer()
        t = datetime.now(timezone.utc)
        inject_a6(mock, t)
        source = mock.send_metric.call_args[0][0]["source"]
        assert source == "OS"

    def test_no_oom_event_in_first_119_calls(self):
        mock = _mock_producer()
        t = datetime.now(timezone.utc)
        for _ in range(119):
            inject_a6(mock, t)
        assert mock.send_event.call_count == 0

    def test_timeout_event_on_120th_call(self):
        mock = _mock_producer()
        t = datetime.now(timezone.utc)
        inject_a6(mock, t)
        for _ in range(119):
            inject_a6(mock, t)
        assert mock.send_event.call_count == 1
        call_args = mock.send_event.call_args[0][0]
        assert call_args["payload"].get("_anomaly_tag") == "A6"
        assert call_args["event_type"] == "TIMEOUT"


class TestInjectA7:
    def test_sends_1_event_message(self):
        mock = _mock_producer()
        t = datetime.now(timezone.utc)
        inject_a7(mock, t)
        assert mock.send_event.call_count == 1

    def test_anomaly_tag_a7_out_of_order(self):
        mock = _mock_producer()
        t = datetime.now(timezone.utc)
        inject_a7(mock, t)
        payload = mock.send_event.call_args[0][0]["payload"]
        assert payload.get("_anomaly_tag") == "A7_OUT_OF_ORDER"

    def test_offset_minus_one_in_payload(self):
        mock = _mock_producer()
        t = datetime.now(timezone.utc)
        inject_a7(mock, t)
        payload = mock.send_event.call_args[0][0]["payload"]
        assert payload.get("offset") == -1


class TestAnomalyRegistry:
    def test_all_7_anomaly_types_in_registry(self):
        names = {entry[0] for entry in ANOMALY_REGISTRY}
        assert names == {"A1", "A2", "A3", "A4", "A5", "A6", "A7"}

    def test_registry_entry_structure(self):
        for entry in ANOMALY_REGISTRY:
            assert len(entry) == 3
            name, fn, cooldown = entry
            assert isinstance(name, str)
            assert callable(fn)
            assert isinstance(cooldown, int)
            assert cooldown > 0

    def test_cooldowns_reasonable(self):
        for _, _, cooldown in ANOMALY_REGISTRY:
            assert cooldown >= 60
