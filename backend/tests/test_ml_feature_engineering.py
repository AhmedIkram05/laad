"""Unit tests for feature engineering — pure functions, no DB needed."""
from __future__ import annotations

import json
import numpy as np
import pytest

from backend.src.anomaly_detection.ml.feature_engineering import extract_features, extract_label, FEATURE_NAMES


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
        assert feat[23] == 1.0, "has_network_disconnect should be 1"

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
        assert feat[7] == 75.5, "os_mem_mean should be 75.5"

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
        assert feat[14] == 2.0, "atm_app_error_count should be 2"
        assert feat[15] == 1.0, "terminal_handler_fatal_count should be 1"

    def test_cassette_empty_count(self):
        rows = [{"source": "HARDWARE", "atm_id": "ATM-GB-0001", "metric_name": None,
                 "metric_value": None, "event_type": "CASSETTE_EMPTY", "severity": "CRITICAL",
                 "raw_payload": {}}]
        feat = extract_features(rows)
        assert feat[17] == 1.0, "hardware_cassette_empty_count should be 1"

    def test_kafka_offline_detected_from_payload(self):
        rows = [{"source": "KAFKA", "atm_id": "ATM-GB-0001", "metric_name": None,
                 "metric_value": None, "event_type": "STATUS", "severity": "INFO",
                 "raw_payload": {"atm_status": "Offline"}}]
        feat = extract_features(rows)
        assert feat[19] == 1.0, "kafka_offline_count should be 1"

    def test_out_of_order_a7_detected(self):
        rows = [{"source": "KAFKA", "atm_id": "ATM-GB-0001", "metric_name": None,
                 "metric_value": None, "event_type": "METRIC", "severity": "INFO",
                 "raw_payload": {"_anomaly_tag": "A7_OUT_OF_ORDER", "offset": -1}}]
        feat = extract_features(rows)
        assert feat[25] == 1.0, "kafka_out_of_order should be 1"

    def test_has_oom_event(self):
        rows = [{"source": "TERMINAL_HANDLER", "atm_id": "ATM-GB-0001", "metric_name": None,
                 "metric_value": None, "event_type": "OOM_ERROR", "severity": "FATAL",
                 "raw_payload": {}}]
        feat = extract_features(rows)
        assert feat[22] == 1.0, "has_oom_event should be 1"

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
        rows = [{"raw_payload": '{"_anomaly_tag": "A3"}'}]
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
        assert len(FEATURE_NAMES) == 26, f"Expected 26 features, got {len(FEATURE_NAMES)}"
        assert all(isinstance(f, str) for f in FEATURE_NAMES), "All FEATURE_NAMES must be strings"