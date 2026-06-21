"""Unit tests for anomaly injectors (Kafka producer-based).

All injectors now accept (producer, timestamp) instead of (cursor, timestamp).
Anomaly tag preservation is verified for A1-A7. A3 and A6 use state-based
progressive emission — one message per call, tracked across calls.
"""
from __future__ import annotations
import pytest
from unittest.mock import MagicMock
from datetime import datetime, timezone

from backend.generator.anomaly_injectors import (
    inject_a1, inject_a2, inject_a3, inject_a4, inject_a5, inject_a6, inject_a7,
    _pick_entity, ANOMALY_REGISTRY,
)
from backend.generator.config import ATMS, SERVERS


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
        # A2 sends 5 messages: 2 CASSETTE_LOW + 2 CASSETTE_EMPTY + 1 KAFKA
        assert mock.send_event.call_count == 5

    def test_anomaly_tag_present(self):
        mock = _mock_producer()
        t = datetime.now(timezone.utc)
        inject_a2(mock, t)
        payloads = [c[0][0]["payload"] for c in mock.send_event.call_args_list]
        assert any(p.get("_anomaly_tag") == "A2" for p in payloads)

    def test_sources_include_hardware_and_kafka(self):
        mock = _mock_producer()
        t = datetime.now(timezone.utc)
        inject_a2(mock, t)
        sources = {c[0][0]["source"] for c in mock.send_event.call_args_list}
        assert "HARDWARE" in sources
        assert "KAFKA" in sources


class TestInjectA3:
    def test_emits_360_metric_messages(self):
        mock = _mock_producer()
        t = datetime.now(timezone.utc)
        inject_a3(mock, t)
        # 90 ticks × 4 metrics per tick = 360 metric messages
        assert mock.send_metric.call_count == 360

    def test_anomaly_tag_present_in_all_metrics(self):
        mock = _mock_producer()
        t = datetime.now(timezone.utc)
        inject_a3(mock, t)
        for call in mock.send_metric.call_args_list:
            assert call[0][0]["payload"].get("_anomaly_tag") == "A3"

    def test_emits_all_90_ticks_in_single_call(self):
        mock = _mock_producer()
        t = datetime.now(timezone.utc)
        inject_a3(mock, t)
        # 90 ticks × 4 metrics per tick = 360 metric messages
        assert mock.send_metric.call_count == 360
        # 1 OOM_ERROR event
        assert mock.send_event.call_count == 1

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

    def test_oom_event_present(self):
        mock = _mock_producer()
        t = datetime.now(timezone.utc)
        inject_a3(mock, t)
        assert mock.send_event.call_count == 1
        call_args = mock.send_event.call_args[0][0]
        assert call_args["payload"].get("_anomaly_tag") == "A3"
        assert call_args["event_type"] == "OutOfMemoryError"

    def test_no_psycopg2_import(self):
        import backend.generator.anomaly_injectors as ai
        assert not hasattr(ai, "psycopg2"), "anomaly_injectors.py must not import psycopg2"
        assert not hasattr(ai, "insert_event"), "anomaly_injectors.py must not have insert_event function"
        assert not hasattr(ai, "insert_metric"), "anomaly_injectors.py must not have insert_metric function"


class TestInjectA4:
    def test_sends_event_and_metric_messages(self):
        mock = _mock_producer()
        t = datetime.now(timezone.utc)
        inject_a4(mock, t)
        # A4 sends 5 events (3 STARTUP + 2 OutOfMemoryError) + 2 metrics (restart_count)
        assert mock.send_event.call_count == 5
        assert mock.send_metric.call_count == 2

    def test_anomaly_tag_present(self):
        mock = _mock_producer()
        t = datetime.now(timezone.utc)
        inject_a4(mock, t)
        payloads = [c[0][0]["payload"] for c in mock.send_event.call_args_list]
        assert any(p.get("_anomaly_tag") == "A4" for p in payloads)

    def test_sources_include_terminal_handler_and_cloud(self):
        mock = _mock_producer()
        t = datetime.now(timezone.utc)
        inject_a4(mock, t)
        event_sources = {c[0][0]["source"] for c in mock.send_event.call_args_list}
        metric_sources = {c[0][0]["source"] for c in mock.send_metric.call_args_list}
        assert "TERMINAL_HANDLER" in event_sources
        assert "CLOUD" in metric_sources


class TestInjectA5:
    def test_sends_variable_event_messages(self):
        mock = _mock_producer()
        t = datetime.now(timezone.utc)
        inject_a5(mock, t)
        # A5 sends 5 events: 3 KAFKA METRIC + 1 ATM_APP TIMEOUT + 1 KAFKA STATUS
        assert mock.send_event.call_count == 5

    def test_anomaly_tag_present_in_all(self):
        mock = _mock_producer()
        t = datetime.now(timezone.utc)
        inject_a5(mock, t)
        for call in mock.send_event.call_args_list:
            assert call[0][0]["payload"].get("_anomaly_tag") == "A5"

    def test_sources_include_kafka_and_atm_app(self):
        mock = _mock_producer()
        t = datetime.now(timezone.utc)
        inject_a5(mock, t)
        sources = {c[0][0]["source"] for c in mock.send_event.call_args_list}
        assert "KAFKA" in sources
        assert "ATM_APP" in sources


class TestInjectA6:
    def test_emits_360_metric_messages(self):
        mock = _mock_producer()
        t = datetime.now(timezone.utc)
        inject_a6(mock, t)
        # 120 ticks × 3 metrics per tick = 360 metric messages
        assert mock.send_metric.call_count == 360
        # 1 TIMEOUT event
        assert mock.send_event.call_count == 1

    def test_metric_name_memory_usage_percent(self):
        mock = _mock_producer()
        t = datetime.now(timezone.utc)
        inject_a6(mock, t)
        metric_names = [c[0][0]["metric_name"] for c in mock.send_metric.call_args_list]
        assert "memory_usage_percent" in metric_names

    def test_source_os(self):
        mock = _mock_producer()
        t = datetime.now(timezone.utc)
        inject_a6(mock, t)
        sources = {c[0][0]["source"] for c in mock.send_metric.call_args_list}
        assert sources == {"OS"}

    def test_timeout_event_present(self):
        mock = _mock_producer()
        t = datetime.now(timezone.utc)
        inject_a6(mock, t)
        assert mock.send_event.call_count == 1
        call_args = mock.send_event.call_args[0][0]
        assert call_args["payload"].get("_anomaly_tag") == "A6"
        assert call_args["event_type"] == "TIMEOUT"


class TestInjectA7:
    def test_sends_event_and_metric_messages(self):
        mock = _mock_producer()
        t = datetime.now(timezone.utc)
        inject_a7(mock, t)
        # A7 sends 2 events (KAFKA out-of-order) + 1 metric (PROMETHEUS malformed)
        assert mock.send_event.call_count == 2
        assert mock.send_metric.call_count == 1

    def test_anomaly_tag_a7_out_of_order(self):
        mock = _mock_producer()
        t = datetime.now(timezone.utc)
        inject_a7(mock, t)
        payloads = [c[0][0]["payload"] for c in mock.send_event.call_args_list]
        assert any(p.get("_anomaly_tag") == "A7_OUT_OF_ORDER" for p in payloads)

    def test_offset_values_in_payload(self):
        mock = _mock_producer()
        t = datetime.now(timezone.utc)
        inject_a7(mock, t)
        payloads = [c[0][0]["payload"] for c in mock.send_event.call_args_list]
        offsets = [p.get("offset") for p in payloads]
        assert 4050 in offsets
        assert 4051 in offsets


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


class TestPickEntity:
    def test_returns_atm_with_zero_server_prob(self):
        for _ in range(100):
            entity = _pick_entity(server_prob=0.0)
            assert entity in ATMS

    def test_returns_server_with_full_server_prob(self):
        for _ in range(100):
            entity = _pick_entity(server_prob=1.0)
            assert entity in SERVERS

    def test_mixed_probability(self):
        count_server = 0
        trials = 1000
        for _ in range(trials):
            entity = _pick_entity(server_prob=0.4)
            if entity in SERVERS:
                count_server += 1
        assert 0.25 <= count_server / trials <= 0.55, f"server ratio {count_server/trials} outside expected range"

    def test_default_probability_is_zero(self):
        for _ in range(100):
            entity = _pick_entity()
            assert entity in ATMS


class TestServerAwareInjectors:
    def test_a3_can_return_server_id(self):
        from unittest.mock import MagicMock
        mock = MagicMock()
        t = datetime.now(timezone.utc)
        results = set()
        for _ in range(50):
            results.add(inject_a3(mock, t))
        has_server = any(r in SERVERS for r in results)
        has_atm = any(r in ATMS for r in results)
        assert has_atm, "A3 should sometimes target ATMs"
        assert has_server, "A3 should sometimes target servers (40% prob over 50 trials)"

    def test_a4_can_return_server_id(self):
        from unittest.mock import MagicMock
        mock = MagicMock()
        t = datetime.now(timezone.utc)
        results = set()
        for _ in range(50):
            results.add(inject_a4(mock, t))
        has_server = any(r in SERVERS for r in results)
        has_atm = any(r in ATMS for r in results)
        assert has_atm, "A4 should sometimes target ATMs"
        assert has_server, "A4 should sometimes target servers (40% prob over 50 trials)"

    def test_a6_can_return_server_id(self):
        from unittest.mock import MagicMock
        mock = MagicMock()
        t = datetime.now(timezone.utc)
        results = set()
        for _ in range(50):
            results.add(inject_a6(mock, t))
        has_server = any(r in SERVERS for r in results)
        has_atm = any(r in ATMS for r in results)
        assert has_atm, "A6 should sometimes target ATMs"
        assert has_server, "A6 should sometimes target servers (40% prob over 50 trials)"

    def test_a1_only_targets_atms(self):
        from unittest.mock import MagicMock
        mock = MagicMock()
        t = datetime.now(timezone.utc)
        for _ in range(100):
            result = inject_a1(mock, t)
            assert result in ATMS, f"A1 should only target ATMs, got {result}"

    def test_a2_only_targets_atms(self):
        from unittest.mock import MagicMock
        mock = MagicMock()
        t = datetime.now(timezone.utc)
        for _ in range(100):
            result = inject_a2(mock, t)
            assert result in ATMS, f"A2 should only target ATMs, got {result}"

    def test_a5_only_targets_atms(self):
        from unittest.mock import MagicMock
        mock = MagicMock()
        t = datetime.now(timezone.utc)
        for _ in range(100):
            result = inject_a5(mock, t)
            assert result in ATMS, f"A5 should only target ATMs, got {result}"

    def test_a7_only_targets_atms(self):
        from unittest.mock import MagicMock
        mock = MagicMock()
        t = datetime.now(timezone.utc)
        for _ in range(100):
            result = inject_a7(mock, t)
            assert result in ATMS, f"A7 should only target ATMs, got {result}"
