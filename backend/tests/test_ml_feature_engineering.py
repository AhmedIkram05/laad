"""Unit tests for feature engineering — pure functions, no DB needed."""
from __future__ import annotations

import numpy as np

from backend.src.anomaly_detection.ml.feature_engineering import extract_features, extract_label, FEATURE_NAMES, FEATURE_COUNT


class TestExtractFeatures:
    def test_returns_correct_shape(self):
        rows = [{"source": "ATM_APP", "atm_id": "ATM-GB-0001", "metric_name": None,
                 "metric_value": None, "event_type": None, "severity": "INFO",
                 "raw_payload": {}}]
        feat = extract_features(rows)
        assert feat.shape == (len(FEATURE_NAMES),), f"Expected {len(FEATURE_NAMES)} features, got {feat.shape}"

    def test_empty_rows_returns_zeros(self):
        feat = extract_features([])
        assert feat.shape == (len(FEATURE_NAMES),)
        assert np.allclose(feat, 0.0)

    def test_string_payload_parsed_transparently(self):
        rows = [{"source": "KAFKA", "atm_id": "ATM-GB-0001", "metric_name": None,
                 "metric_value": None, "event_type": "METRIC", "severity": "INFO",
                 "raw_payload": '{"response_time_ms": 1500.0}'}]
        feat = extract_features(rows)
        assert feat.shape == (len(FEATURE_NAMES),)

    def test_dict_payload_handled(self):
        rows = [{"source": "ATM_APP", "atm_id": "ATM-GB-0001", "metric_name": None,
                 "metric_value": None, "event_type": "NETWORK_DISCONNECT", "severity": "ERROR",
                 "raw_payload": {"_anomaly_tag": "A1", "atm_status": "Offline"}}]
        feat = extract_features(rows)
        assert feat.shape == (len(FEATURE_NAMES),)
        idx_ndc = FEATURE_NAMES.index("network_disconnect_count")
        idx_tag = FEATURE_NAMES.index("anomaly_tag_count")
        idx_has_nd = FEATURE_NAMES.index("has_network_disconnect")
        idx_has_nd2 = FEATURE_NAMES.index("has_network_disconnect")
        assert feat[idx_ndc] == 1.0, f"network_disconnect_count should be 1, got {feat[idx_ndc]}"
        assert feat[idx_tag] == 1.0, f"anomaly_tag_count should be 1, got {feat[idx_tag]}"
        assert feat[idx_has_nd] == 1.0, f"has_network_disconnect should be 1, got {feat[idx_has_nd]}"

    def test_jvm_memory_metric_increases_rate(self):
        now = 1700000000.0
        rows = [
            {"source": "PROMETHEUS", "atm_id": "ATM-GB-0001",
             "metric_name": "jvm_memory_used_bytes", "metric_value": 1e8,
             "event_type": None, "severity": None, "raw_payload": {},
             "timestamp": now - 120},
            {"source": "PROMETHEUS", "atm_id": "ATM-GB-0001",
             "metric_name": "jvm_memory_used_bytes", "metric_value": 2e8,
             "event_type": None, "severity": None, "raw_payload": {},
             "timestamp": now - 60},
            {"source": "PROMETHEUS", "atm_id": "ATM-GB-0001",
             "metric_name": "jvm_memory_used_bytes", "metric_value": 3e8,
             "event_type": None, "severity": None, "raw_payload": {},
             "timestamp": now},
        ]
        feat = extract_features(rows)
        assert feat[0] > 0, "jvm_mem_mean should be > 0"
        assert feat[2] > 0, "jvm_mem_rate should be > 0"

    def test_os_memory_metric_extracted(self):
        rows = [{"source": "OS", "atm_id": "ATM-GB-0002",
                 "metric_name": "windows_os_snapshot", "metric_value": 75.5,
                 "event_type": None, "severity": None, "raw_payload": {}}]
        feat = extract_features(rows)
        assert feat[8] == 75.5, f"os_mem_mean should be 75.5, got {feat[8]}"

    def test_error_counts_per_source(self):
        rows = [
            {"source": "ATM_APP", "atm_id": "ATM-GB-0001", "metric_name": None,
             "metric_value": None, "event_type": "NETWORK_DISCONNECT", "severity": "ERROR",
             "raw_payload": {}},
            {"source": "ATM_APP", "atm_id": "ATM-GB-0001", "metric_name": None,
             "metric_value": None, "event_type": "TIMEOUT", "severity": "CRITICAL",
             "raw_payload": {}},
            {"source": "TERMINAL_HANDLER", "atm_id": "ATM-GB-0001", "metric_name": None,
             "metric_value": None, "event_type": "OOM_ERROR", "severity": "FATAL",
             "raw_payload": {}},
        ]
        feat = extract_features(rows)
        idx_err = FEATURE_NAMES.index("atm_app_error_count")
        idx_fatal = FEATURE_NAMES.index("terminal_handler_fatal_count")
        idx_oom = FEATURE_NAMES.index("terminal_handler_oom_count")
        idx_has_oom = FEATURE_NAMES.index("has_oom_event")
        assert feat[idx_err] == 2.0, f"atm_app_error_count should be 2, got {feat[idx_err]}"
        assert feat[idx_fatal] == 1.0, f"terminal_handler_fatal_count should be 1, got {feat[idx_fatal]}"
        assert feat[idx_oom] == 1.0, f"terminal_handler_oom_count should be 1, got {feat[idx_oom]}"
        assert feat[idx_has_oom] == 1.0, f"has_oom_event should be 1, got {feat[idx_has_oom]}"

    def test_cassette_empty_count(self):
        rows = [{"source": "HARDWARE", "atm_id": "ATM-GB-0001", "metric_name": None,
                 "metric_value": None, "event_type": "CASSETTE_EMPTY", "severity": "CRITICAL",
                 "raw_payload": {}}]
        feat = extract_features(rows)
        idx = FEATURE_NAMES.index("hardware_cassette_empty_count")
        assert feat[idx] == 1.0, f"hardware_cassette_empty_count should be 1, got {feat[idx]}"

    def test_kafka_offline_detected_from_payload(self):
        rows = [{"source": "KAFKA", "atm_id": "ATM-GB-0001", "metric_name": None,
                 "metric_value": None, "event_type": "STATUS", "severity": "INFO",
                 "raw_payload": {"atm_status": "Offline"}}]
        feat = extract_features(rows)
        idx = FEATURE_NAMES.index("kafka_offline_count")
        assert feat[idx] == 1.0, f"kafka_offline_count should be 1, got {feat[idx]}"

    def test_out_of_order_a7_detected(self):
        rows = [{"source": "KAFKA", "atm_id": "ATM-GB-0001", "metric_name": None,
                 "metric_value": None, "event_type": "METRIC", "severity": "INFO",
                 "raw_payload": {"_anomaly_tag": "A7_OUT_OF_ORDER", "offset": -1}}]
        feat = extract_features(rows)
        idx = FEATURE_NAMES.index("kafka_out_of_order")
        assert feat[idx] == 1.0, f"kafka_out_of_order should be 1, got {feat[idx]}"
        idx_tag = FEATURE_NAMES.index("anomaly_tag_count")
        assert feat[idx_tag] == 1.0, f"anomaly_tag_count should be 1, got {feat[idx_tag]}"

    def test_has_oom_event(self):
        rows = [{"source": "TERMINAL_HANDLER", "atm_id": "ATM-GB-0001", "metric_name": None,
                 "metric_value": None, "event_type": "OOM_ERROR", "severity": "FATAL",
                 "raw_payload": {}}]
        feat = extract_features(rows)
        idx = FEATURE_NAMES.index("has_oom_event")
        assert feat[idx] == 1.0, f"has_oom_event should be 1, got {feat[idx]}"

    def test_unknown_payload_ignored_gracefully(self):
        rows = [{"source": "UNKNOWN", "atm_id": None, "metric_name": None,
                 "metric_value": "not_a_number", "event_type": None, "severity": None,
                 "raw_payload": None}]
        feat = extract_features(rows)
        assert feat.shape == (len(FEATURE_NAMES),)
        assert not np.any(np.isnan(feat)), "No NaN values from unknown/malformed data"


class TestExtractLabel:
    def test_no_tags_returns_none(self):
        rows = [{"raw_payload": {}}, {"raw_payload": {"foo": "bar"}}]
        assert extract_label(rows) is None

    def test_a1_tag_extracted(self):
        rows = [{"raw_payload": {"_anomaly_tag": "A1", "extra": "data"}}]
        assert extract_label(rows) == "A1"

    def test_a7_out_of_order_tag(self):
        rows = [{"raw_payload": {"_anomaly_tag": "A7_OUT_OF_ORDER"}}]
        assert extract_label(rows) == "A7"

    def test_string_payload_parsed(self):
        rows = [{"raw_payload": {"_anomaly_tag": "A3"}}, {"raw_payload": {"_anomaly_tag": "A3"}}, {"raw_payload": {"_anomaly_tag": "A3"}}]
        assert extract_label(rows) == "A3"

    def test_legacy_anomaly_tag(self):
        rows = [{"raw_payload": {"_anomaly": "A5"}}]
        assert extract_label(rows) == "A5"

    def test_dominant_tag_returned(self):
        rows = [
            {"raw_payload": {"_anomaly_tag": "A1"}},
            {"raw_payload": {"_anomaly_tag": "A1"}},
            {"raw_payload": {"_anomaly_tag": "A1"}},
            {"raw_payload": {"_anomaly_tag": "A2"}},
            {"raw_payload": {"_anomaly_tag": "A2"}},
        ]
        assert extract_label(rows) == "A1"

    def test_mixed_tags_returns_none(self):
        rows = [{"raw_payload": {"foo": "A1"}}, {"raw_payload": {"bar": "A2"}}]
        assert extract_label(rows) is None

    def test_invalid_tag_format_ignored(self):
        rows = [{"raw_payload": {"_anomaly_tag": "B1"}}, {"raw_payload": {"_anomaly_tag": "A9"}}]
        assert extract_label(rows) is None

    def test_none_raw_payload_skipped(self):
        rows = [{"raw_payload": None}, {"raw_payload": {"_anomaly_tag": "A4"}}]
        assert extract_label(rows) == "A4"


class TestFeatureNames:
    def test_feature_count_matches_extract_output(self):
        rows = [{"source": "ATM_APP", "atm_id": "ATM-GB-0001", "metric_name": None,
                 "metric_value": None, "event_type": None, "severity": None,
                 "raw_payload": {}}]
        feat = extract_features(rows)
        assert len(FEATURE_NAMES) == len(feat), \
            f"FEATURE_NAMES has {len(FEATURE_NAMES)} entries but extract_features returned {len(feat)} values"

    def test_all_features_named(self):
        assert len(FEATURE_NAMES) == FEATURE_COUNT, f"Expected {FEATURE_COUNT} features, got {len(FEATURE_NAMES)}"
        assert all(isinstance(f, str) for f in FEATURE_NAMES), "All FEATURE_NAMES must be strings"