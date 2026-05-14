"""Unit tests for ML anomaly detector — mocks DB and model files."""
from __future__ import annotations

import numpy as np
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

import pytest

from backend.src.anomaly_detection.ml.ml_detector import (
    MLAnomalyDetector, ARTIFACT_DIR, WINDOW_SECONDS, CONFIDENCE_THRESHOLD,
    SIGNAL_CORRELATOR_ENABLED,
    TITLE_MAP, SOURCES_MAP, RECOMMENDED_ACTIONS_MAP,
)
from backend.src.anomaly_detection.ml.feature_engineering import FEATURE_COUNT


@pytest.fixture(autouse=True)
def _patch_mlflow():
    with patch("backend.src.anomaly_detection.ml.ml_detector.mlflow"):
        yield


class TestLoadModels:
    def test_loads_successfully_when_artifacts_exist(self, tmp_path):
        mock_iso = MagicMock()
        mock_clf = MagicMock()
        mock_le  = MagicMock()

        with patch("backend.src.anomaly_detection.ml.ml_detector.ARTIFACT_DIR", tmp_path):
            with patch("backend.src.anomaly_detection.ml.ml_detector.joblib.load") as jl:
                jl.side_effect = [mock_iso, mock_clf, mock_le]
                detector = MLAnomalyDetector()

        assert detector._loaded is True
        assert detector._iso is mock_iso
        assert detector._clf is mock_clf
        assert detector._le  is mock_le

    def test_returns_false_when_artifact_missing(self, tmp_path):
        with patch("backend.src.anomaly_detection.ml.ml_detector.ARTIFACT_DIR", tmp_path):
            with patch("backend.src.anomaly_detection.ml.ml_detector.joblib.load",
                       side_effect=FileNotFoundError("artifacts not found")):
                detector = MLAnomalyDetector()

        assert detector._loaded is False


class TestQueryWindow:
    def test_queries_and_returns_tuple(self):
        detector = MLAnomalyDetector()
        detector._loaded = True

        mock_rows = [
            {"timestamp": "2025-01-01T12:00:00Z", "source": "ATM_APP",
             "atm_id": "ATM-GB-0001", "metric_name": None,
             "metric_value": None, "event_type": "ACTIVITY",
             "severity": "INFO", "raw_payload": {},
             "correlation_id": None, "transaction_id": None,
             "atm_status": None, "component": None},
        ]

        with patch("backend.src.anomaly_detection.ml.ml_detector.get_cursor") as mock_gc:
            mock_cur = MagicMock()
            mock_cur.__enter__  = MagicMock(return_value=mock_cur)
            mock_cur.__exit__   = MagicMock(return_value=None)
            mock_cur.fetchall.return_value = [dict(r) for r in mock_rows]
            mock_gc.return_value = mock_cur

            rows, window_start, window_end = detector._query_window()

        assert len(rows) == 1
        assert rows[0]["source"] == "ATM_APP"
        assert isinstance(window_start, datetime)
        assert isinstance(window_end, datetime)


class TestIsActive:
    def test_returns_true_when_active_anomaly_exists(self):
        detector = MLAnomalyDetector()
        detector._loaded = True

        with patch("backend.src.anomaly_detection.ml.ml_detector.get_cursor") as mock_gc:
            mock_cur = MagicMock()
            mock_cur.__enter__  = MagicMock(return_value=mock_cur)
            mock_cur.__exit__   = MagicMock(return_value=None)
            mock_cur.fetchone.return_value = {"?column?": 1}
            mock_gc.return_value = mock_cur

            result = detector._is_active("A1", "ATM-GB-0001")

        assert result is True

    def test_returns_false_when_no_active_anomaly(self):
        detector = MLAnomalyDetector()
        detector._loaded = True

        with patch("backend.src.anomaly_detection.ml.ml_detector.get_cursor") as mock_gc:
            mock_cur = MagicMock()
            mock_cur.__enter__  = MagicMock(return_value=mock_cur)
            mock_cur.__exit__   = MagicMock(return_value=None)
            mock_cur.fetchone.return_value = None
            mock_gc.return_value = mock_cur

            result = detector._is_active("A1", "ATM-GB-0001")

        assert result is False


class TestDetectHeuristic:
    def test_calls_detect_anomalies_from_window(self):
        detector = MLAnomalyDetector()
        rows = [{"source": "ATM_APP", "event_type": "NETWORK_DISCONNECT", "error_code": "ERR-0040",
                 "atm_id": "ATM-GB-0003", "timestamp": "2025-01-01T10:00:00Z",
                 "raw_payload": {}, "metric_name": None, "metric_value": None, "severity": "ERROR"}]
        with patch("backend.src.anomaly_detection.ml.ml_detector.detect_anomalies_from_window") as mock_detect:
            mock_detect.return_value = [
                {"anomaly_type": "A1", "atm_id": "ATM-GB-0003", "severity": "CRITICAL",
                 "title": "ATM offline due to network failure.",
                 "explanation": {"network_disconnect": True},
                 "sources_involved": ["ATM_APP", "KAFKA", "TERMINAL_HANDLER"],
                 "recommended_action": "Check network.", "correlation_id": None}
            ]
            result = detector._detect_heuristic(rows, datetime.now(timezone.utc), datetime.now(timezone.utc))

        assert len(result) == 1
        assert result[0]["anomaly_type"] == "A1"
        mock_detect.assert_called_once()

    def test_returns_empty_on_empty_rows(self):
        detector = MLAnomalyDetector()
        result = detector._detect_heuristic([], None, None)
        assert result == []


class TestDetectAndSave:
    def test_skips_when_fewer_than_5_rows(self):
        detector = MLAnomalyDetector()
        detector._loaded = True

        with patch.object(detector, "_query_window", return_value=([{"x": 1}] * 4, None, None)):
            result = detector.detect_and_save()

        assert result == 0

    def test_heuristic_runs_and_saves_when_enabled(self):
        detector = MLAnomalyDetector()
        detector._loaded = False

        rows = [{"source": "ATM_APP", "event_type": "NETWORK_DISCONNECT", "error_code": "ERR-0040",
                 "atm_id": "ATM-GB-0003", "timestamp": "2025-01-01T10:00:00Z",
                 "raw_payload": {}, "metric_name": None, "metric_value": None, "severity": "ERROR"}
                for _ in range(10)]

        with patch.object(detector, "_query_window", return_value=(rows, None, None)):
            with patch.object(detector, "_detect_heuristic", return_value=[
                {"anomaly_type": "A1", "atm_id": "ATM-GB-0003", "severity": "CRITICAL",
                 "title": "ATM offline due to network failure.",
                 "explanation": {"network_disconnect": True},
                 "sources_involved": ["ATM_APP", "KAFKA", "TERMINAL_HANDLER"],
                 "recommended_action": "Check network.", "correlation_id": "corr-001"}
            ]):
                with patch.object(detector, "_is_active", return_value=False):
                    with patch.object(detector, "_save_anomaly") as mock_save:
                        result = detector.detect_and_save()

        assert result == 1
        mock_save.assert_called_once()
        call_kwargs = mock_save.call_args.kwargs
        assert call_kwargs["anomaly_type"] == "A1"
        assert call_kwargs["atm_id"] == "ATM-GB-0003"
        assert call_kwargs["source"] == "SIGNAL_CORRELATOR"
        assert call_kwargs["sources_involved"] == ["ATM_APP", "KAFKA", "TERMINAL_HANDLER"]
        assert "recommended_action" in call_kwargs

    def test_ml_runs_when_models_loaded_and_iso_flags_anomaly(self):
        detector = MLAnomalyDetector()
        detector._loaded = True

        fake_features = np.zeros(FEATURE_COUNT, dtype=np.float32)

        mock_iso = MagicMock()
        mock_iso.predict.return_value = np.array([-1])

        mock_clf = MagicMock()
        mock_clf.predict_proba.return_value = np.array([[0.05] * 8 + [0.8]])

        mock_le = MagicMock()
        mock_le.inverse_transform.return_value = ["A7"]

        rows = [{"atm_id": "ATM-GB-0001", "source": "KAFKA",
                 "metric_name": None, "metric_value": None,
                 "event_type": "METRIC", "severity": "INFO", "raw_payload": {},
                 "timestamp": "2025-01-01T10:00:00Z"}
                for _ in range(10)]

        with patch.object(detector, "_query_window", return_value=(rows, None, None)):
            with patch.object(detector, "_detect_heuristic", return_value=[]):

                    with patch("backend.src.anomaly_detection.ml.ml_detector.extract_features", return_value=fake_features):
                        with patch.object(detector, "_iso", mock_iso):
                            with patch.object(detector, "_clf", mock_clf):
                                with patch.object(detector, "_le", mock_le):
                                    with patch.object(detector, "_is_active", return_value=False):
                                        with patch.object(detector, "_save_anomaly") as mock_save:
                                            result = detector.detect_and_save()

        assert result == 1
        call_kwargs = mock_save.call_args.kwargs
        assert call_kwargs["anomaly_type"] == "A7"
        assert call_kwargs["source"] == "CLASSIFIER"
        assert call_kwargs["confidence"] == 0.8

    def test_ml_skips_when_confidence_below_threshold(self):
        detector = MLAnomalyDetector()
        detector._loaded = True

        fake_features = np.zeros(FEATURE_COUNT, dtype=np.float32)

        mock_iso = MagicMock()
        mock_iso.predict.return_value = np.array([-1])

        mock_clf = MagicMock()
        mock_clf.predict_proba.return_value = np.array([[0.05] * 8 + [0.3]])

        mock_le = MagicMock()
        mock_le.inverse_transform.return_value = ["A7"]

        rows = [{"atm_id": "ATM-GB-0001", "source": "KAFKA",
                 "metric_name": None, "metric_value": None,
                 "event_type": "METRIC", "severity": "INFO", "raw_payload": {},
                 "timestamp": "2025-01-01T10:00:00Z"}
                for _ in range(10)]

        with patch.object(detector, "_query_window", return_value=(rows, None, None)):
            with patch.object(detector, "_detect_heuristic", return_value=[]):

                    with patch("backend.src.anomaly_detection.ml.ml_detector.extract_features", return_value=fake_features):
                        with patch.object(detector, "_iso", mock_iso):
                            with patch.object(detector, "_clf", mock_clf):
                                with patch.object(detector, "_le", mock_le):
                                    with patch.object(detector, "_is_active", return_value=False):
                                        with patch.object(detector, "_save_anomaly") as mock_save:
                                            result = detector.detect_and_save()

        assert result == 0
        mock_save.assert_not_called()

    def test_ml_skips_when_iso_says_normal(self):
        detector = MLAnomalyDetector()
        detector._loaded = True

        fake_features = np.zeros(FEATURE_COUNT, dtype=np.float32)

        mock_iso = MagicMock()
        mock_iso.predict.return_value = np.array([1])

        rows = [{"atm_id": "ATM-GB-0001", "source": "KAFKA",
                 "metric_name": None, "metric_value": None,
                 "event_type": "METRIC", "severity": "INFO", "raw_payload": {},
                 "timestamp": "2025-01-01T10:00:00Z"}
                for _ in range(10)]

        with patch.object(detector, "_query_window", return_value=(rows, None, None)):
            with patch.object(detector, "_detect_heuristic", return_value=[]):

                    with patch("backend.src.anomaly_detection.ml.ml_detector.extract_features", return_value=fake_features):
                        with patch.object(detector, "_iso", mock_iso):
                            with patch.object(detector, "_is_active", return_value=False):
                                with patch.object(detector, "_save_anomaly") as mock_save:
                                    result = detector.detect_and_save()

        assert result == 0
        mock_save.assert_not_called()

    def test_ml_detects_unknown_when_iso_score_extreme(self):
        detector = MLAnomalyDetector()
        detector._loaded = True

        fake_features = np.zeros(FEATURE_COUNT, dtype=np.float32)

        mock_iso = MagicMock()
        mock_iso.predict.return_value = np.array([-1])
        mock_iso.score_samples.return_value = np.array([-0.25])

        mock_clf = MagicMock()
        mock_clf.predict_proba.return_value = np.array([[0.9]])
        mock_clf.predict.return_value = np.array([0])

        mock_le = MagicMock()
        mock_le.inverse_transform.return_value = ["NORMAL"]

        rows = [{"atm_id": "ATM-GB-0001", "source": "ATM_APP",
                 "metric_name": None, "metric_value": None,
                 "event_type": "ACTIVITY", "severity": "INFO", "raw_payload": {},
                 "timestamp": "2025-01-01T10:00:00Z"}
                for _ in range(10)]

        with patch.object(detector, "_query_window", return_value=(rows, None, None)):
            with patch.object(detector, "_detect_heuristic", return_value=[]):

                    with patch("backend.src.anomaly_detection.ml.ml_detector.extract_features", return_value=fake_features):
                        with patch.object(detector, "_iso", mock_iso):
                            with patch.object(detector, "_clf", mock_clf):
                                with patch.object(detector, "_le", mock_le):
                                    with patch.object(detector, "_is_active", return_value=False):
                                        with patch.object(detector, "_save_anomaly") as mock_save:
                                            result = detector.detect_and_save()

        assert result == 1
        call_kwargs = mock_save.call_args.kwargs
        assert call_kwargs["anomaly_type"] == "UNKNOWN"
        assert call_kwargs["source"] == "CLASSIFIER"

    def test_ml_skips_unknown_when_iso_score_mild(self):
        detector = MLAnomalyDetector()
        detector._loaded = True

        fake_features = np.zeros(FEATURE_COUNT, dtype=np.float32)

        mock_iso = MagicMock()
        mock_iso.predict.return_value = np.array([-1])
        mock_iso.score_samples.return_value = np.array([-0.05])

        mock_clf = MagicMock()
        mock_clf.predict_proba.return_value = np.array([[0.9]])
        mock_clf.predict.return_value = np.array([0])

        mock_le = MagicMock()
        mock_le.inverse_transform.return_value = ["NORMAL"]

        rows = [{"atm_id": "ATM-GB-0001", "source": "ATM_APP",
                 "metric_name": None, "metric_value": None,
                 "event_type": "ACTIVITY", "severity": "INFO", "raw_payload": {},
                 "timestamp": "2025-01-01T10:00:00Z"}
                for _ in range(10)]

        with patch.object(detector, "_query_window", return_value=(rows, None, None)):
            with patch.object(detector, "_detect_heuristic", return_value=[]):

                    with patch("backend.src.anomaly_detection.ml.ml_detector.extract_features", return_value=fake_features):
                        with patch.object(detector, "_iso", mock_iso):
                            with patch.object(detector, "_clf", mock_clf):
                                with patch.object(detector, "_le", mock_le):
                                    with patch.object(detector, "_is_active", return_value=False):
                                        with patch.object(detector, "_save_anomaly") as mock_save:
                                            result = detector.detect_and_save()

        assert result == 0
        mock_save.assert_not_called()

    def test_ml_skips_when_xgb_classifies_normal(self):
        detector = MLAnomalyDetector()
        detector._loaded = True

        fake_features = np.zeros(FEATURE_COUNT, dtype=np.float32)

        mock_iso = MagicMock()
        mock_iso.predict.return_value = np.array([-1])

        mock_clf = MagicMock()
        mock_clf.predict_proba.return_value = np.array([[0.9]])
        mock_clf.predict.return_value = np.array([0])

        mock_le = MagicMock()
        mock_le.inverse_transform.return_value = ["NORMAL"]

        rows = [{"atm_id": "ATM-GB-0001", "source": "KAFKA",
                 "metric_name": None, "metric_value": None,
                 "event_type": "METRIC", "severity": "INFO", "raw_payload": {},
                 "timestamp": "2025-01-01T10:00:00Z"}
                for _ in range(10)]

        with patch.object(detector, "_query_window", return_value=(rows, None, None)):
            with patch.object(detector, "_detect_heuristic", return_value=[]):

                    with patch("backend.src.anomaly_detection.ml.ml_detector.extract_features", return_value=fake_features):
                        with patch.object(detector, "_iso", mock_iso):
                            with patch.object(detector, "_clf", mock_clf):
                                with patch.object(detector, "_le", mock_le):
                                    with patch.object(detector, "_is_active", return_value=False):
                                        with patch.object(detector, "_save_anomaly") as mock_save:
                                            result = detector.detect_and_save()

        assert result == 0
        mock_save.assert_not_called()


class TestSaveAnomaly:
    def test_save_anomaly_populates_sources_and_recommended_action(self):
        detector = MLAnomalyDetector()
        detector._loaded = True

        with patch("backend.src.anomaly_detection.ml.ml_detector.get_cursor") as mock_gc:
            mock_cur = MagicMock()
            mock_cur.__enter__  = MagicMock(return_value=mock_cur)
            mock_cur.__exit__   = MagicMock(return_value=None)
            mock_gc.return_value = mock_cur

            with patch.object(detector, "_is_active", return_value=False):
                detector._save_anomaly(
                    anomaly_type="A1",
                    atm_id="ATM-GB-0003",
                    confidence=0.95,
                    source="HEURISTIC",
                    explanation={"network_disconnect": True},
                    sources_involved=["ATM_APP", "KAFKA", "TERMINAL_HANDLER"],
                    recommended_action="Check network.",
                    correlation_id="corr-001",
                )

            mock_cur.execute.assert_called_once()
            call_args = mock_cur.execute.call_args[0]
            insert_sql = call_args[0]
            params = call_args[1]
            assert "sources_involved" in insert_sql
            assert "recommended_action" in insert_sql
            assert "correlation_id" in insert_sql
            assert params[7] == "Check network."
            assert params[8] == '["ATM_APP", "KAFKA", "TERMINAL_HANDLER"]'
            assert params[9] == "corr-001"

    def test_save_anomaly_skips_when_already_active(self):
        detector = MLAnomalyDetector()
        detector._loaded = True

        with patch.object(detector, "_is_active", return_value=True):
            with patch("backend.src.anomaly_detection.ml.ml_detector.get_cursor") as mock_gc:
                mock_cur = MagicMock()
                mock_gc.return_value = mock_cur
                detector._save_anomaly("A1", "ATM-GB-0001", 0.95)
                mock_cur.execute.assert_not_called()


class TestConstants:
    def test_confidence_threshold_is_060(self):
        assert CONFIDENCE_THRESHOLD == 0.60

    def test_window_seconds_is_600(self):
        assert WINDOW_SECONDS == 600

    def test_artifact_dir_points_to_backend_ml(self):
        assert "backend" in str(ARTIFACT_DIR) and "ml" in str(ARTIFACT_DIR)

    def test_all_a_types_have_title(self):
        for atype in ["A1","A2","A3","A4","A5","A6","A7"]:
            assert atype in TITLE_MAP
            assert TITLE_MAP[atype]

    def test_all_a_types_have_sources(self):
        for atype in ["A1","A2","A3","A4","A5","A6","A7"]:
            assert atype in SOURCES_MAP
            assert len(SOURCES_MAP[atype]) > 0

    def test_all_a_types_have_recommended_action(self):
        for atype in ["A1","A2","A3","A4","A5","A6","A7"]:
            assert atype in RECOMMENDED_ACTIONS_MAP
            assert len(RECOMMENDED_ACTIONS_MAP[atype]) > 10

    def test_signal_correlator_enabled_by_default(self):
        assert SIGNAL_CORRELATOR_ENABLED is True


class TestAttribution:
    def test_returns_mode_for_unknown_type(self):
        detector = MLAnomalyDetector()
        rows = [
            {"atm_id": "ATM-GB-0001"}, {"atm_id": "ATM-GB-0001"}, {"atm_id": "ATM-GB-0002"},
        ]
        result = detector._attribution_for("A1", rows)
        assert result == "ATM-GB-0001"

    def test_returns_pod_for_a3(self):
        detector = MLAnomalyDetector()
        rows = [
            {"atm_id": "ATM-GB-0001", "raw_payload": {"pod_name": "terminal-handler-7"}},
            {"atm_id": "ATM-GB-0002", "raw_payload": {"pod_name": "terminal-handler-7"}},
        ]
        result = detector._attribution_for("A3", rows)
        assert result == "terminal-handler-7"

    def test_returns_pod_for_a4(self):
        detector = MLAnomalyDetector()
        rows = [
            {"atm_id": "ATM-GB-0001", "raw_payload": {"pod_name": "atm-service-3"}},
        ]
        result = detector._attribution_for("A4", rows)
        assert result == "atm-service-3"

    def test_returns_pod_for_a7(self):
        detector = MLAnomalyDetector()
        rows = [
            {"atm_id": "ATM-GB-0001", "raw_payload": {"entity_id": "kafka-partition-2"}},
        ]
        result = detector._attribution_for("A7", rows)
        assert result == "kafka-partition-2"

    def test_returns_mode_when_no_pod(self):
        detector = MLAnomalyDetector()
        rows = [
            {"atm_id": "ATM-GB-0003"}, {"atm_id": "ATM-GB-0003"}, {"atm_id": "ATM-GB-0003"},
        ]
        result = detector._attribution_for("A3", rows)
        assert result == "ATM-GB-0003"

    def test_returns_none_when_empty(self):
        detector = MLAnomalyDetector()
        result = detector._attribution_for("A1", [])
        assert result is None

    def test_parses_string_payload_for_pod(self):
        detector = MLAnomalyDetector()
        rows = [
            {"atm_id": "ATM-GB-0001", "raw_payload": '{"pod_name": "service-x", "atm_id": "ATM-GB-0005"}'},
        ]
        result = detector._attribution_for("A3", rows)
        assert result == "service-x"


class TestQueryWindowFallback:
    def test_min_rows_threshold(self):
        detector = MLAnomalyDetector()
        detector._loaded = True
        with patch.object(detector, "_query_window") as mock_qw:
            mock_qw.return_value = ([{"x": 1}] * 4, None, None)
            result = detector.detect_and_save()
            assert result == 0


class TestRollingBaseline:
    def test_not_ready_until_5_windows(self):
        from backend.src.anomaly_detection.ml.ml_detector import RollingBaseline
        rb = RollingBaseline(window_size=5)
        feat = np.zeros(47, dtype=np.float32)
        for i in range(4):
            rb.update(feat + i)
            assert rb.ready is False, f"Should not be ready after {i+1} windows"
        rb.update(feat + 4)
        assert rb.ready is True

    def test_z_scores_zero_when_no_baseline(self):
        from backend.src.anomaly_detection.ml.ml_detector import RollingBaseline
        rb = RollingBaseline(window_size=5)
        feat = np.ones(47, dtype=np.float32)
        z = rb.compute_z_scores(feat)
        assert np.allclose(z, 0.0)

    def test_z_scores_normalize_to_baseline(self):
        from backend.src.anomaly_detection.ml.ml_detector import RollingBaseline
        rb = RollingBaseline(window_size=5)
        base = np.array([100.0] * 47, dtype=np.float32)
        for i in range(5):
            rb.update(base + np.random.randn(47).astype(np.float32) * 0.1)
        feat_outlier = base + 50.0
        z = rb.compute_z_scores(feat_outlier)
        max_z = float(np.max(np.abs(z)))
        assert max_z > 3.0, f"Outlier should have z > 3, got {max_z}"

    def test_baseline_features_shape(self):
        from backend.src.anomaly_detection.ml.ml_detector import RollingBaseline
        rb = RollingBaseline(window_size=5)
        feat = np.zeros(47, dtype=np.float32)
        for i in range(5):
            rb.update(feat + i * 10)
        bf = rb.compute_baseline_features(feat + 100)
        assert len(bf) == 13
        assert bf[0] > 0, "max_abs_z should be positive for a large deviation"
