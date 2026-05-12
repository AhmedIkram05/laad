"""Unit tests for ML anomaly detector — mocks DB and model files."""
from __future__ import annotations

import numpy as np
from unittest.mock import MagicMock, patch

import pytest

from backend.src.anomaly_detection.ml.ml_detector import (
    MLAnomalyDetector, ARTIFACT_DIR, WINDOW_SECONDS, CONFIDENCE_THRESHOLD
)


class TestLoadModels:
    def test_loads_successfully_when_artifacts_exist(self, tmp_path):
        mock_iso = MagicMock()
        mock_clf = MagicMock()
        mock_le  = MagicMock()

        detector = MLAnomalyDetector()
        with patch("backend.src.anomaly_detection.ml.ml_detector.ARTIFACT_DIR", tmp_path):
            with patch("joblib.load") as jl:
                jl.side_effect = [mock_iso, mock_clf, mock_le]
                result = detector._load_models()

        assert result is True
        assert detector._iso is mock_iso
        assert detector._clf is mock_clf
        assert detector._le  is mock_le
        assert detector._loaded is True

    def test_returns_false_when_artifact_missing(self, tmp_path):
        detector = MLAnomalyDetector()
        with patch("backend.src.anomaly_detection.ml.ml_detector.ARTIFACT_DIR", tmp_path):
            with patch("joblib.load", side_effect=FileNotFoundError("artifacts not found")):
                result = detector._load_models()

        assert result is False
        assert detector._loaded is False


class TestQueryWindow:
    def test_queries_with_correct_rows(self):
        detector = MLAnomalyDetector()
        detector._loaded = True

        mock_rows = [
            {"timestamp": "2025-01-01T12:00:00Z", "source": "ATM_APP",
             "atm_id": "ATM-GB-0001", "metric_name": None,
             "metric_value": None, "event_type": "ACTIVITY",
             "severity": "INFO", "raw_payload": {}}
        ]

        with patch("backend.src.anomaly_detection.ml.ml_detector.get_cursor") as mock_gc:
            mock_cur = MagicMock()
            mock_cur.__enter__  = MagicMock(return_value=mock_cur)
            mock_cur.__exit__   = MagicMock(return_value=None)
            mock_cur.fetchall.return_value = [dict(r) for r in mock_rows]
            mock_gc.return_value = mock_cur

            rows = detector._query_window()

        assert len(rows) == 1
        assert rows[0]["source"] == "ATM_APP"


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


class TestDetectAndSave:
    def test_skips_when_fewer_than_5_rows(self):
        detector = MLAnomalyDetector()
        detector._loaded = True

        with patch.object(detector, "_query_window", return_value=[{"x": 1}] * 4):
            result = detector.detect_and_save()

        assert result == 0

    def test_falls_back_when_models_not_loaded(self):
        detector = MLAnomalyDetector()
        detector._loaded = False

        with patch.object(detector, "_load_models", return_value=False):
            with patch("backend.src.anomaly_detection.ml.ml_detector.FALLBACK_ENABLED", True):
                with patch("backend.src.anomaly_detection.ml.ml_detector.get_cursor") as mock_gc:
                    mock_cur = MagicMock()
                    mock_cur.__enter__  = MagicMock(return_value=mock_cur)
                    mock_cur.__exit__   = MagicMock(return_value=None)
                    mock_gc.return_value = mock_cur

                    with patch("backend.src.anomaly_detection.anomaly_detector.AnomalyDetector") as MockRD:
                        mock_rd = MockRD.return_value
                        mock_rd.load_data.return_value = []
                        mock_rd.detect_anomalies.return_value = []
                        mock_rd.save_anomalies.return_value = None

                        result = detector.detect_and_save()

        assert result == 0

    def test_returns_zero_when_iso_forest_says_normal(self):
        detector = MLAnomalyDetector()
        detector._loaded = True

        fake_features = np.zeros(26, dtype=np.float32)

        mock_iso = MagicMock()
        mock_iso.predict.return_value = np.array([1])

        rows = [{"atm_id": "ATM-GB-0001"} for _ in range(10)]

        with patch.object(detector, "_query_window", return_value=rows):
            with patch("backend.src.anomaly_detection.ml.ml_detector.extract_features", return_value=fake_features):
                with patch.object(detector, "_iso", mock_iso):
                    result = detector.detect_and_save()

        assert result == 0

    def test_detects_and_saves_anomaly_when_confidence_above_threshold(self):
        detector = MLAnomalyDetector()
        detector._loaded = True

        fake_features = np.zeros(26, dtype=np.float32)

        mock_iso = MagicMock()
        mock_iso.predict.return_value = np.array([-1])

        mock_clf = MagicMock()
        mock_clf.predict_proba.return_value = np.array([[0.05] * 8 + [0.8]])

        mock_le = MagicMock()
        mock_le.inverse_transform.return_value = ["A7"]

        rows = [{"atm_id": "ATM-GB-0001", "source": "KAFKA",
                 "metric_name": None, "metric_value": None,
                 "event_type": "METRIC", "severity": "INFO", "raw_payload": {}}
                for _ in range(10)]

        with patch.object(detector, "_query_window", return_value=rows):
            with patch("backend.src.anomaly_detection.ml.ml_detector.extract_features", return_value=fake_features):
                with patch.object(detector, "_iso", mock_iso):
                    with patch.object(detector, "_clf", mock_clf):
                        with patch.object(detector, "_le", mock_le):
                            with patch.object(detector, "_is_active", return_value=False):
                                with patch.object(detector, "_save_anomaly"):
                                    result = detector.detect_and_save()

        assert result == 1

    def test_skips_when_confidence_below_threshold(self):
        detector = MLAnomalyDetector()
        detector._loaded = True

        fake_features = np.zeros(26, dtype=np.float32)

        mock_iso = MagicMock()
        mock_iso.predict.return_value = np.array([-1])

        mock_clf = MagicMock()
        mock_clf.predict_proba.return_value = np.array([[0.05] * 8 + [0.3]])

        mock_le = MagicMock()
        mock_le.inverse_transform.return_value = ["A7"]

        rows = [{"atm_id": "ATM-GB-0001"} for _ in range(10)]

        with patch.object(detector, "_query_window", return_value=rows):
            with patch("backend.src.anomaly_detection.ml.ml_detector.extract_features", return_value=fake_features):
                with patch.object(detector, "_iso", mock_iso):
                    with patch.object(detector, "_clf", mock_clf):
                        with patch.object(detector, "_le", mock_le):
                            with patch.object(detector, "_is_active", return_value=False):
                                with patch.object(detector, "_fallback_to_rules"):
                                    result = detector.detect_and_save()

        assert result == 0

    def test_skips_when_prediction_is_normal(self):
        detector = MLAnomalyDetector()
        detector._loaded = True

        fake_features = np.zeros(26, dtype=np.float32)

        mock_iso = MagicMock()
        mock_iso.predict.return_value = np.array([-1])

        mock_clf = MagicMock()
        mock_clf.predict_proba.return_value = np.array([[0.9]])
        mock_clf.predict.return_value = np.array([0])

        mock_le = MagicMock()
        mock_le.inverse_transform.return_value = ["NORMAL"]

        rows = [{"atm_id": "ATM-GB-0001"} for _ in range(10)]

        with patch.object(detector, "_query_window", return_value=rows):
            with patch("backend.src.anomaly_detection.ml.ml_detector.extract_features", return_value=fake_features):
                with patch.object(detector, "_iso", mock_iso):
                    with patch.object(detector, "_clf", mock_clf):
                        with patch.object(detector, "_le", mock_le):
                            result = detector.detect_and_save()

        assert result == 0


class TestConstants:
    def test_confidence_threshold_is_060(self):
        assert CONFIDENCE_THRESHOLD == 0.60

    def test_window_seconds_is_300(self):
        assert WINDOW_SECONDS == 300

    def test_artifact_dir_points_to_backend_ml(self):
        assert "backend" in str(ARTIFACT_DIR) and "ml" in str(ARTIFACT_DIR)