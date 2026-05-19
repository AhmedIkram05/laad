"""Tests for the standalone detection functions and AnomalyDetector class."""
import pytest
from datetime import datetime, timezone
import json

from backend.src.anomaly_detection.anomaly_detector import (
    a1_detection, a2_detection, a3_detection, a4_detection,
    a5_detection, a6_detection, a7_detection,
    detect_anomalies_from_window,
    _payload_get, _as_float,
    AnomalyDetector,
)


class TestHelpers:
    def test_payload_get_from_column(self):
        row = {"my_key": "value1", "payload": json.dumps({"my_key": "value2"})}
        assert _payload_get(row, "my_key") == "value1"

    def test_payload_get_from_payload_string(self):
        row = {"payload": json.dumps({"my_key": "value2"})}
        assert _payload_get(row, "my_key") == "value2"

    def test_payload_get_from_raw_payload_dict(self):
        row = {"raw_payload": {"my_key": "value3"}}
        assert _payload_get(row, "my_key") == "value3"

    def test_payload_get_missing(self):
        row = {"payload": json.dumps({"other_key": "value"})}
        assert _payload_get(row, "my_key") is None

    def test_as_float_valid(self):
        assert _as_float(10) == 10.0
        assert _as_float("10.5") == 10.5

    def test_as_float_invalid(self):
        assert _as_float(None) is None
        assert _as_float("invalid") is None


class TestA1Detection:
    def test_fires_when_all_six_signals_present(self):
        data = [
            {"source": "ATM_APP", "atm_id": "ATM-GB-0003", "event_type": "NETWORK_DISCONNECT",
             "error_code": "ERR-0040", "timestamp": "2024-01-01T10:00:00Z"},
            {"source": "ATM_APP", "atm_id": "ATM-GB-0003", "event_type": "TIMEOUT",
             "response_time_ms": 30000, "timestamp": "2024-01-01T10:00:01Z"},
            {"source": "KAFKA", "atm_id": "ATM-GB-0003", "atm_status": "Offline",
             "transaction_failure_reason": "HOST_UNAVAILABLE", "timestamp": "2024-01-01T10:00:02Z"},
            {"source": "TERMINAL_HANDLER", "atm_id": "ATM-GB-0003", "event_type": "NETWORK_TIMEOUT",
             "timestamp": "2024-01-01T10:00:03Z"},
        ]
        anomalies = a1_detection(data)
        assert len(anomalies) == 1
        assert anomalies[0]["anomaly_type"] == "A1"
        assert anomalies[0]["atm_id"] == "ATM-GB-0003"
        assert anomalies[0]["severity"] == "CRITICAL"
        assert anomalies[0]["sources_involved"] == ["ATM_APP", "KAFKA", "TERMINAL_HANDLER"]
        assert "recommended_action" in anomalies[0]
        assert len(anomalies[0]["recommended_action"]) > 10

    def test_does_not_fire_when_missing_signal(self):
        data = [
            {"source": "ATM_APP", "atm_id": "ATM-GB-0003", "event_type": "NETWORK_DISCONNECT",
             "error_code": "ERR-0040", "timestamp": "2024-01-01T10:00:00Z"},
            {"source": "ATM_APP", "atm_id": "ATM-GB-0003", "event_type": "TIMEOUT",
             "response_time_ms": 30000, "timestamp": "2024-01-01T10:00:01Z"},
        ]
        anomalies = a1_detection(data)
        assert len(anomalies) == 0

    def test_requires_at_least_three_signals(self):
        data = [
            {"source": "ATM_APP", "atm_id": "ATM-GB-0003", "event_type": "NETWORK_DISCONNECT",
             "error_code": "ERR-0040", "timestamp": "2024-01-01T10:00:00Z"},
            {"source": "KAFKA", "atm_id": "ATM-GB-0003", "atm_status": "Offline",
             "transaction_failure_reason": "HOST_UNAVAILABLE", "timestamp": "2024-01-01T10:00:02Z"},
            {"source": "TERMINAL_HANDLER", "atm_id": "ATM-GB-0003", "event_type": "NETWORK_TIMEOUT",
             "timestamp": "2024-01-01T10:00:03Z"},
        ]
        anomalies = a1_detection(data)
        assert len(anomalies) == 1


class TestA2Detection:
    def test_fires_when_cassettes_empty_and_kafka_confirms(self):
        data = [
            {"source": "HARDWARE", "atm_id": "ATM-A2", "event_type": "CASSETTE_LOW",
             "timestamp": "2024-01-01T10:00:00Z"},
            {"source": "HARDWARE", "atm_id": "ATM-A2", "event_type": "CASSETTE_LOW",
             "timestamp": "2024-01-01T10:00:01Z"},
            {"source": "HARDWARE", "atm_id": "ATM-A2", "event_type": "CASSETTE_EMPTY",
             "timestamp": "2024-01-01T10:00:02Z"},
            {"source": "HARDWARE", "atm_id": "ATM-A2", "event_type": "CASSETTE_EMPTY",
             "timestamp": "2024-01-01T10:00:03Z"},
            {"source": "KAFKA", "atm_id": "ATM-A2", "atm_status": "Out of Service",
             "timestamp": "2024-01-01T10:00:04Z"},
        ]
        anomalies = a2_detection(data)
        assert len(anomalies) == 1
        assert anomalies[0]["anomaly_type"] == "A2"
        assert anomalies[0]["atm_id"] == "ATM-A2"
        assert anomalies[0]["sources_involved"] == ["HARDWARE", "KAFKA"]

    def test_requires_at_least_one_empty_cassette(self):
        data = [
            {"source": "HARDWARE", "atm_id": "ATM-A2", "event_type": "CASSETTE_EMPTY",
             "timestamp": "2024-01-01T10:00:02Z"},
            {"source": "KAFKA", "atm_id": "ATM-A2", "atm_status": "Out of Service",
             "timestamp": "2024-01-01T10:00:04Z"},
        ]
        anomalies = a2_detection(data)
        assert len(anomalies) == 1


class TestA3Detection:
    def test_fires_when_jvm_memory_rises_and_oom_present(self):
        data = [
            {"source": "PROMETHEUS", "metric_name": "jvm_memory_used_bytes",
             "pod_name": "pod-1", "metric_value": 300, "timestamp": "2024-01-01T10:00:00Z"},
            {"source": "PROMETHEUS", "metric_name": "jvm_memory_used_bytes",
             "pod_name": "pod-1", "metric_value": 700, "timestamp": "2024-01-01T10:45:00Z"},
            {"source": "PROMETHEUS", "metric_name": "jvm_memory_used_bytes",
             "pod_name": "pod-1", "metric_value": 1040, "timestamp": "2024-01-01T11:29:00Z"},
            {"source": "TERMINAL_HANDLER", "event_type": "OOM_ERROR",
             "pod_name": "pod-1", "timestamp": "2024-01-01T11:30:00Z"},
        ]
        anomalies = a3_detection(data)
        assert len(anomalies) == 1
        assert anomalies[0]["anomaly_type"] == "A3"
        assert anomalies[0]["sources_involved"] == ["PROMETHEUS", "TERMINAL_HANDLER"]
        assert anomalies[0]["atm_id"] is None

    def test_does_not_fire_without_oom(self):
        data = [
            {"source": "PROMETHEUS", "metric_name": "jvm_memory_used_bytes",
             "pod_name": "pod-1", "metric_value": 300, "timestamp": "2024-01-01T10:00:00Z"},
            {"source": "PROMETHEUS", "metric_name": "jvm_memory_used_bytes",
             "pod_name": "pod-1", "metric_value": 1040, "timestamp": "2024-01-01T11:29:00Z"},
        ]
        anomalies = a3_detection(data)
        assert len(anomalies) == 0

    def test_a3_fires_with_OutOfMemoryError(self):
        data = [
            {"source": "PROMETHEUS", "metric_name": "jvm_memory_used_bytes",
             "pod_name": "pod-1", "metric_value": 300_000_000, "timestamp": "2024-01-01T10:00:00Z"},
            {"source": "PROMETHEUS", "metric_name": "jvm_memory_used_bytes",
             "pod_name": "pod-1", "metric_value": 700_000_000, "timestamp": "2024-01-01T10:45:00Z"},
            {"source": "PROMETHEUS", "metric_name": "jvm_memory_used_bytes",
             "pod_name": "pod-1", "metric_value": 1_040_000_000, "timestamp": "2024-01-01T11:29:00Z"},
            {"source": "TERMINAL_HANDLER", "event_type": "OutOfMemoryError",
             "pod_name": "pod-1", "timestamp": "2024-01-01T11:30:00Z"},
        ]
        anomalies = a3_detection(data)
        assert len(anomalies) == 1
        assert anomalies[0]["anomaly_type"] == "A3"

    def test_a3_attributes_to_atm_id_when_provided(self):
        data = [
            {"source": "PROMETHEUS", "metric_name": "jvm_memory_used_bytes",
             "pod_name": "ATM-GB-0003", "metric_value": 300, "timestamp": "2024-01-01T10:00:00Z"},
            {"source": "PROMETHEUS", "metric_name": "jvm_memory_used_bytes",
             "pod_name": "ATM-GB-0003", "metric_value": 700, "timestamp": "2024-01-01T10:45:00Z"},
            {"source": "PROMETHEUS", "metric_name": "jvm_memory_used_bytes",
             "pod_name": "ATM-GB-0003", "metric_value": 1040, "timestamp": "2024-01-01T11:29:00Z"},
            {"source": "TERMINAL_HANDLER", "event_type": "OOM_ERROR",
             "pod_name": "ATM-GB-0003", "atm_id": "ATM-GB-0003",
             "timestamp": "2024-01-01T11:30:00Z"},
        ]
        anomalies = a3_detection(data)
        assert len(anomalies) == 1
        assert anomalies[0]["atm_id"] == "ATM-GB-0003"
        expl = json.loads(anomalies[0]["explanation"])
        assert expl["atm_id"] == "ATM-GB-0003"

    def test_a3_evaluates_multiple_pods_independently(self):
        data = [
            {"source": "PROMETHEUS", "metric_name": "jvm_memory_used_bytes",
             "pod_name": "pod-A", "metric_value": 300, "timestamp": "2024-01-01T10:00:00Z"},
            {"source": "PROMETHEUS", "metric_name": "jvm_memory_used_bytes",
             "pod_name": "pod-A", "metric_value": 500, "timestamp": "2024-01-01T10:45:00Z"},
            {"source": "PROMETHEUS", "metric_name": "jvm_memory_used_bytes",
             "pod_name": "pod-A", "metric_value": 700, "timestamp": "2024-01-01T11:29:00Z"},
            {"source": "TERMINAL_HANDLER", "event_type": "OOM_ERROR",
             "pod_name": "pod-A", "timestamp": "2024-01-01T11:30:00Z"},
            {"source": "PROMETHEUS", "metric_name": "jvm_memory_used_bytes",
             "pod_name": "pod-B", "metric_value": 100, "timestamp": "2024-01-01T10:00:00Z"},
            {"source": "PROMETHEUS", "metric_name": "jvm_memory_used_bytes",
             "pod_name": "pod-B", "metric_value": 150, "timestamp": "2024-01-01T11:29:00Z"},
        ]
        anomalies = a3_detection(data)
        assert len(anomalies) == 1
        assert anomalies[0]["anomaly_type"] == "A3"
        expl = json.loads(anomalies[0]["explanation"])
        assert expl["pod"] == "pod-A"


class TestA4Detection:
    def test_fires_when_gcp_restarts_and_terminal_handler_confirms(self):
        data = [
            {"source": "GCP", "metric_name": "container/restart_count",
             "metric_value": 1, "timestamp": "2024-01-01T09:30:00Z", "atm_id": "ATM-A4"},
            {"source": "GCP", "metric_name": "container/restart_count",
             "metric_value": 2, "timestamp": "2024-01-01T09:34:00Z", "atm_id": "ATM-A4"},
            {"source": "TERMINAL_HANDLER", "event_type": "STARTUP",
             "timestamp": "2024-01-01T09:30:00Z", "atm_id": "ATM-A4"},
            {"source": "TERMINAL_HANDLER", "event_type": "STARTUP",
             "timestamp": "2024-01-01T09:32:00Z", "atm_id": "ATM-A4"},
            {"source": "TERMINAL_HANDLER", "event_type": "STARTUP",
             "timestamp": "2024-01-01T09:34:00Z", "atm_id": "ATM-A4"},
        ]
        anomalies = a4_detection(data)
        assert len(anomalies) == 1
        assert anomalies[0]["anomaly_type"] == "A4"
        assert anomalies[0]["sources_involved"] == ["GCP", "TERMINAL_HANDLER"]

    def test_requires_at_least_one_gcp_restart(self):
        data = [
            {"source": "TERMINAL_HANDLER", "event_type": "STARTUP",
             "timestamp": "2024-01-01T09:30:00Z", "atm_id": "ATM-A4"},
            {"source": "TERMINAL_HANDLER", "event_type": "STARTUP",
             "timestamp": "2024-01-01T09:32:00Z", "atm_id": "ATM-A4"},
            {"source": "TERMINAL_HANDLER", "event_type": "STARTUP",
             "timestamp": "2024-01-01T09:34:00Z", "atm_id": "ATM-A4"},
        ]
        anomalies = a4_detection(data)
        assert len(anomalies) == 0

    def test_a4_fires_with_real_gcp_parser_format(self):
        data = [
            {"source": "CLOUD", "metric_name": "restart_count",
             "metric_value": 1, "timestamp": "2024-01-01T09:30:00Z", "atm_id": "ATM-A4"},
            {"source": "CLOUD", "metric_name": "restart_count",
             "metric_value": 2, "timestamp": "2024-01-01T09:34:00Z", "atm_id": "ATM-A4"},
            {"source": "TERMINAL_HANDLER", "event_type": "STARTUP",
             "timestamp": "2024-01-01T09:30:00Z", "atm_id": "ATM-A4"},
            {"source": "TERMINAL_HANDLER", "event_type": "STARTUP",
             "timestamp": "2024-01-01T09:32:00Z", "atm_id": "ATM-A4"},
            {"source": "TERMINAL_HANDLER", "event_type": "STARTUP",
             "timestamp": "2024-01-01T09:34:00Z", "atm_id": "ATM-A4"},
        ]
        anomalies = a4_detection(data)
        assert len(anomalies) == 1
        assert anomalies[0]["anomaly_type"] == "A4"


class TestA5Detection:
    def test_fires_when_kafka_rt_spikes_and_atm_app_times_out(self):
        data = [
            {"source": "KAFKA", "atm_id": "ATM-A5", "response_time_ms": 3200,
             "timestamp": "2024-01-01T09:30:00Z"},
            {"source": "KAFKA", "atm_id": "ATM-A5", "response_time_ms": 30000,
             "timestamp": "2024-01-01T09:31:00Z"},
            {"source": "ATM_APP", "atm_id": "ATM-A5", "event_type": "TIMEOUT",
             "error_code": "ERR-0012", "timestamp": "2024-01-01T09:32:00Z"},
        ]
        anomalies = a5_detection(data)
        assert len(anomalies) == 1
        assert anomalies[0]["anomaly_type"] == "A5"
        assert anomalies[0]["atm_id"] == "ATM-A5"
        assert anomalies[0]["sources_involved"] == ["KAFKA", "ATM_APP"]

    def test_requires_at_least_two_rt_spikes(self):
        data = [
            {"source": "KAFKA", "atm_id": "ATM-A5", "response_time_ms": 3200,
             "timestamp": "2024-01-01T09:30:00Z"},
            {"source": "ATM_APP", "atm_id": "ATM-A5", "event_type": "TIMEOUT",
             "error_code": "ERR-0012", "timestamp": "2024-01-01T09:32:00Z"},
        ]
        anomalies = a5_detection(data)
        assert len(anomalies) == 0


class TestA6Detection:
    def test_fires_when_os_memory_high_and_timeout_present(self):
        data = [
            {"source": "OS", "atm_id": "ATM-A6", "memory_usage_percent": 46.0,
             "timestamp": "2024-01-01T09:30:00Z"},
            {"source": "OS", "atm_id": "ATM-A6", "memory_usage_percent": 92.0,
             "timestamp": "2024-01-01T09:40:00Z"},
            {"source": "OS", "atm_id": "ATM-A6", "memory_usage_percent": 98.75,
             "timestamp": "2024-01-01T09:45:00Z"},
            {"source": "ATM_APP", "atm_id": "ATM-A6", "event_type": "TIMEOUT",
             "error_detail": "ThreadAbortException",
             "timestamp": "2024-01-01T09:46:00Z"},
        ]
        anomalies = a6_detection(data)
        assert len(anomalies) == 1
        assert anomalies[0]["anomaly_type"] == "A6"
        assert anomalies[0]["atm_id"] == "ATM-A6"
        assert anomalies[0]["sources_involved"] == ["OS", "ATM_APP"]

    def test_requires_memory_threshold_or_increase_plus_timeout(self):
        data = [
            {"source": "OS", "atm_id": "ATM-A6", "memory_usage_percent": 30.0,
             "timestamp": "2024-01-01T09:30:00Z"},
            {"source": "ATM_APP", "atm_id": "ATM-A6", "event_type": "TIMEOUT",
             "error_detail": "ThreadAbortException",
             "timestamp": "2024-01-01T09:46:00Z"},
        ]
        anomalies = a6_detection(data)
        assert len(anomalies) == 0


class TestA7Detection:
    def test_fires_with_out_of_order_kafka_and_malformed_prometheus(self):
        data = [
            {"source": "KAFKA", "atm_id": "ATM-A7", "raw_payload": json.dumps({"kafka_offset": 4050}),
             "timestamp": "2024-01-01T09:30:00Z", "atm_status": None},
            {"source": "KAFKA", "atm_id": "ATM-A7", "raw_payload": json.dumps({"kafka_offset": 4051}),
             "timestamp": "2024-01-01T09:28:00Z"},
            {"source": "PROMETHEUS", "metric_name": "some_metric",
             "metric_value": "890iembre", "timestamp": "2024-01-01T09:33:00Z"},
        ]
        anomalies = a7_detection(data, ingestion_errors=[])
        assert len(anomalies) >= 1
        assert anomalies[0]["anomaly_type"] == "A7"
        assert anomalies[0]["sources_involved"] == ["KAFKA", "PROMETHEUS"]

    def test_ingestion_errors_pairs_produce_a7(self):
        data = []
        ingestion_errors = [
            {"id": 1, "ts": datetime(2024, 1, 1, 9, 30, tzinfo=timezone.utc),
             "source": "PROMETHEUS", "raw_input": "{}", "error_detail": "parse error"},
            {"id": 2, "ts": datetime(2024, 1, 1, 9, 32, tzinfo=timezone.utc),
             "source": "KAFKA", "raw_input": "{}", "error_detail": "decode error"},
        ]
        anomalies = a7_detection(data, ingestion_errors=ingestion_errors)
        a7_types = [a for a in anomalies if a["anomaly_type"] == "A7"]
        assert len(a7_types) >= 1

    def test_malformed_prometheus_alone_fires_global_a7(self):
        data = [
            {"source": "PROMETHEUS", "metric_name": "cpu_usage",
             "metric_value": "890iembre", "timestamp": "2024-01-01T09:33:00Z"},
        ]
        anomalies = a7_detection(data, ingestion_errors=[])
        assert len(anomalies) == 1
        assert anomalies[0]["anomaly_type"] == "A7"


class TestDetectAnomaliesFromWindow:
    def test_runs_all_seven_detectors_and_deduplicates(self):
        data = [
            {"source": "ATM_APP", "atm_id": "ATM-GB-0003", "event_type": "NETWORK_DISCONNECT",
             "error_code": "ERR-0040", "timestamp": "2024-01-01T10:00:00Z"},
            {"source": "ATM_APP", "atm_id": "ATM-GB-0003", "event_type": "TIMEOUT",
             "response_time_ms": 30000, "timestamp": "2024-01-01T10:00:01Z"},
            {"source": "KAFKA", "atm_id": "ATM-GB-0003", "atm_status": "Offline",
             "transaction_failure_reason": "HOST_UNAVAILABLE",
             "timestamp": "2024-01-01T10:00:02Z"},
            {"source": "TERMINAL_HANDLER", "atm_id": "ATM-GB-0003", "event_type": "NETWORK_TIMEOUT",
             "timestamp": "2024-01-01T10:00:03Z"},
        ]
        anomalies = detect_anomalies_from_window(data)
        assert len(anomalies) == 1
        assert anomalies[0]["anomaly_type"] == "A1"
        assert anomalies[0]["recommended_action"] is not None

    def test_returns_empty_for_normal_data(self):
        data = [
            {"source": "ATM_APP", "atm_id": "ATM-GB-0001", "event_type": "ACTIVITY",
             "severity": "INFO", "timestamp": "2024-01-01T10:00:00Z"},
        ]
        anomalies = detect_anomalies_from_window(data)
        assert anomalies == []

    def test_respects_time_window_for_ingestion_errors(self):
        window_start = datetime(2024, 1, 1, 9, 0, tzinfo=timezone.utc)
        window_end = datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc)
        data = []
        ingestion_errors = [
            {"id": 1, "ts": datetime(2024, 1, 1, 9, 30, tzinfo=timezone.utc),
             "source": "PROMETHEUS", "raw_input": "{}", "error_detail": "parse error"},
            {"id": 2, "ts": datetime(2024, 1, 1, 9, 32, tzinfo=timezone.utc),
             "source": "KAFKA", "raw_input": "{}", "error_detail": "decode error"},
        ]
        anomalies = detect_anomalies_from_window(data, window_start, window_end)
        assert anomalies == []


class TestAnomalyDetectorClass:
    def test_detect_anomalies_from_window_delegates_to_function(self):
        detector = AnomalyDetector()
        data = [
            {"source": "ATM_APP", "atm_id": "ATM-A2", "event_type": "CASSETTE_EMPTY",
             "timestamp": "2024-01-01T10:00:02Z"},
            {"source": "ATM_APP", "atm_id": "ATM-A2", "event_type": "CASSETTE_EMPTY",
             "timestamp": "2024-01-01T10:00:03Z"},
            {"source": "KAFKA", "atm_id": "ATM-A2", "atm_status": "Out of Service",
             "timestamp": "2024-01-01T10:00:04Z"},
        ]
        anomalies = detector.detect_anomalies_from_window(data)
        assert len(anomalies) == 1
        assert anomalies[0]["anomaly_type"] == "A2"
