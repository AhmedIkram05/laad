import pytest
from datetime import datetime, timezone
import json

from backend.src.anomaly_detection.anomaly_detector import AnomalyDetector

@pytest.fixture
def detector():
    return AnomalyDetector(":memory:")

def test_payload_get(detector):
    # Test getting directly from column
    row1 = {"my_key": "value1", "payload": json.dumps({"my_key": "value2"})}
    assert detector._payload_get(row1, "my_key") == "value1"

    # Test getting from payload string
    row2 = {"payload": json.dumps({"my_key": "value2"})}
    assert detector._payload_get(row2, "my_key") == "value2"

    # Test getting from raw_payload dict
    row3 = {"raw_payload": {"my_key": "value3"}}
    assert detector._payload_get(row3, "my_key") == "value3"

    # Test missing key
    row4 = {"payload": json.dumps({"other_key": "value"})}
    assert detector._payload_get(row4, "my_key") is None

def test_as_float(detector):
    assert detector._as_float(10) == 10.0
    assert detector._as_float("10.5") == 10.5
    assert detector._as_float(None) is None
    assert detector._as_float("invalid") is None

def test_a1_detection(detector):
    data = [
        {"timestamp": "2024-01-01T10:00:00Z", "source": "ATM_APP", "atm_id": "ATM-GB-0003", "event_type": "NETWORK_DISCONNECT", "error_code": "ERR-0040"},
        {"timestamp": "2024-01-01T10:00:01Z", "source": "ATM_APP", "atm_id": "ATM-GB-0003", "event_type": "TIMEOUT", "response_time_ms": 30000},
        {"timestamp": "2024-01-01T10:00:02Z", "source": "KAFKA", "atm_id": "ATM-GB-0003", "atm_status": "Offline", "transaction_failure_reason": "HOST_UNAVAILABLE"},
        {"timestamp": "2024-01-01T10:00:03Z", "source": "TERMINAL_HANDLER", "atm_id": "ATM-GB-0003", "event_type": "NETWORK_TIMEOUT"}
    ]

    anomalies = detector.a1_detection(data)
    assert len(anomalies) == 1
    anomaly = anomalies[0]
    assert anomaly["anomaly_type"] == "A1"
    assert anomaly["atm_id"] == "ATM-GB-0003"
    assert anomaly["severity"] == "CRITICAL"
    assert anomaly["title"] == "ATM offline due to network failure."

def test_a2_detection(detector):
    data = [
        {"atm_id": "ATM-A2", "event_type": "CASSETTE_LOW", "timestamp": "2024-01-01T10:00:00Z"},
        {"atm_id": "ATM-A2", "event_type": "CASSETTE_LOW", "timestamp": "2024-01-01T10:00:01Z"},
        {"atm_id": "ATM-A2", "event_type": "CASSETTE_EMPTY", "timestamp": "2024-01-01T10:00:02Z"},
        {"atm_id": "ATM-A2", "event_type": "CASSETTE_EMPTY", "timestamp": "2024-01-01T10:00:03Z"},
        {"source": "KAFKA", "atm_id": "ATM-A2", "atm_status": "Out of Service", "timestamp": "2024-01-01T10:00:04Z"}
    ]
    anomalies = detector.a2_detection(data)
    assert len(anomalies) == 1
    assert anomalies[0]["anomaly_type"] == "A2"
    assert anomalies[0]["atm_id"] == "ATM-A2"

def test_a3_detection(detector):
    data = [
        {"source": "PROMETHEUS", "metric_name": "jvm_memory_used_bytes", "pod_name": "pod-1", "metric_value": 300, "timestamp": "2024-01-01T10:00:00Z"},
        {"source": "PROMETHEUS", "metric_name": "jvm_memory_used_bytes", "pod_name": "pod-1", "metric_value": 700, "timestamp": "2024-01-01T10:45:00Z"},
        {"source": "PROMETHEUS", "metric_name": "jvm_memory_used_bytes", "pod_name": "pod-1", "metric_value": 1040, "timestamp": "2024-01-01T11:29:00Z"},
        {"source": "TERMINAL_HANDLER", "event_type": "OOM_ERROR", "pod_name": "pod-1", "timestamp": "2024-01-01T11:30:00Z"}
    ]
    anomalies = detector.a3_detection(data)
    assert len(anomalies) == 1
    assert anomalies[0]["anomaly_type"] == "A3"

def test_a4_detection(detector):
    data = [
        {"source": "GCP", "metric_name": "container/restart_count", "metric_value": 1, "timestamp": "2024-01-01T09:30:00Z"},
        {"source": "GCP", "metric_name": "container/restart_count", "metric_value": 2, "timestamp": "2024-01-01T09:34:00Z"},
        {"source": "TERMINAL_HANDLER", "event_type": "STARTUP", "timestamp": "2024-01-01T09:30:00Z"},
        {"source": "TERMINAL_HANDLER", "event_type": "STARTUP", "timestamp": "2024-01-01T09:32:00Z"},
        {"source": "TERMINAL_HANDLER", "event_type": "STARTUP", "timestamp": "2024-01-01T09:34:00Z"}
    ]
    anomalies = detector.a4_detection(data)
    assert len(anomalies) == 1
    assert anomalies[0]["anomaly_type"] == "A4"

def test_a5_detection(detector):
    data = [
        {"source": "KAFKA", "atm_id": "ATM-A5", "response_time_ms": 3200, "timestamp": "2024-01-01T09:30:00Z"},
        {"source": "KAFKA", "atm_id": "ATM-A5", "response_time_ms": 30000, "timestamp": "2024-01-01T09:31:00Z"},
        {"source": "ATM_APP", "atm_id": "ATM-A5", "event_type": "TIMEOUT", "error_code": "ERR-0012", "timestamp": "2024-01-01T09:32:00Z"}
    ]
    anomalies = detector.a5_detection(data)
    assert len(anomalies) == 1
    assert anomalies[0]["anomaly_type"] == "A5"
    assert anomalies[0]["atm_id"] == "ATM-A5"

def test_a6_detection(detector):
    data = [
        {"source": "OS", "atm_id": "ATM-A6", "memory_usage_percent": 46.0, "timestamp": "2024-01-01T09:30:00Z"},
        {"source": "OS", "atm_id": "ATM-A6", "memory_usage_percent": 92.0, "timestamp": "2024-01-01T09:40:00Z"},
        {"source": "OS", "atm_id": "ATM-A6", "memory_usage_percent": 98.75, "timestamp": "2024-01-01T09:45:00Z"},
        {"source": "ATM_APP", "atm_id": "ATM-A6", "event_type": "TIMEOUT", "error_detail": "ThreadAbortException", "timestamp": "2024-01-01T09:46:00Z"}
    ]
    anomalies = detector.a6_detection(data)
    assert len(anomalies) == 1
    assert anomalies[0]["anomaly_type"] == "A6"
    assert anomalies[0]["atm_id"] == "ATM-A6"

def test_a7_detection(detector):
    data = [
        {"source": "KAFKA", "atm_id": "ATM-A7", "payload": json.dumps({"kafka_offset": 4050}), "timestamp": "2024-01-01T09:30:00Z", "atm_status": "Offline"},
        {"source": "KAFKA", "atm_id": "ATM-A7", "payload": json.dumps({"kafka_offset": 4051}), "timestamp": "2024-01-01T09:28:00Z"},
        {"source": "PROMETHEUS", "metric_name": "some_metric", "metric_value": "890iembre", "timestamp": "2024-01-01T09:33:00Z"}
    ]
    anomalies = detector.a7_detection(data)
    assert len(anomalies) >= 1
    assert anomalies[0]["anomaly_type"] == "A7"

