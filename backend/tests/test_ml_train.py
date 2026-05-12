"""Unit tests for ML training pipeline — mocks DB."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from backend.src.anomaly_detection.ml.train import (
    load_windows, train, ARTIFACT_DIR, WINDOW_SECONDS,
    STEP_SECONDS, IF_CONTAMINATION, XGB_N_ESTIMATORS, MLFLOW_EXPERIMENT
)


class TestLoadWindows:
    def test_returns_empty_when_no_rows(self):
        with patch("backend.src.anomaly_detection.ml.train.get_cursor") as mock_gc:
            mock_cur = MagicMock()
            mock_cur.__enter__  = MagicMock(return_value=mock_cur)
            mock_cur.__exit__   = MagicMock(return_value=None)
            mock_cur.fetchall.return_value = []
            mock_gc.return_value = mock_cur

            features, labels = load_windows(minutes=10)

        assert features == []
        assert labels == []

    def test_queries_with_correct_cutoff(self):
        with patch("backend.src.anomaly_detection.ml.train.get_cursor") as mock_gc:
            mock_cur = MagicMock()
            mock_cur.__enter__  = MagicMock(return_value=mock_cur)
            mock_cur.__exit__   = MagicMock(return_value=None)
            mock_cur.fetchall.return_value = []
            mock_gc.return_value = mock_cur

            load_windows(minutes=30)

        mock_cur.execute.assert_called_once()
        call_args = mock_cur.execute.call_args
        query = call_args[0][0]
        params = call_args[0][1]
        assert "v_unified_analysis" in query
        assert len(params) == 1

    def test_skips_windows_with_fewer_than_5_rows(self):
        now = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

        rows = [
            dict(timestamp=now - timedelta(seconds=10 * i), source="ATM_APP",
                 atm_id="ATM-GB-0001", metric_name=None, metric_value=None,
                 event_type="ACTIVITY", severity="INFO", raw_payload={})
            for i in range(3)
        ]

        with patch("backend.src.anomaly_detection.ml.train.get_cursor") as mock_gc:
            mock_cur = MagicMock()
            mock_cur.__enter__  = MagicMock(return_value=mock_cur)
            mock_cur.__exit__   = MagicMock(return_value=None)
            mock_cur.fetchall.return_value = rows
            mock_gc.return_value = mock_cur

            features, labels = load_windows(minutes=1)

        assert features == []

    def test_creates_windows_from_db_rows(self):
        now = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

        rows = [
            dict(timestamp=now - timedelta(seconds=60 * (9 - i)),
                 source="ATM_APP", atm_id="ATM-GB-0001",
                 metric_name=None, metric_value=None,
                 event_type="ACTIVITY", severity="INFO",
                 raw_payload={"_anomaly_tag": "A1"} if i == 0 else {})
            for i in range(10)
        ]

        with patch("backend.src.anomaly_detection.ml.train.get_cursor") as mock_gc:
            mock_cur = MagicMock()
            mock_cur.__enter__  = MagicMock(return_value=mock_cur)
            mock_cur.__exit__   = MagicMock(return_value=None)
            mock_cur.fetchall.return_value = rows
            mock_gc.return_value = mock_cur

            features, labels = load_windows(minutes=5)

        assert len(features) > 0, "Should produce at least one window"
        for f in features:
            assert isinstance(f, np.ndarray)
            assert len(f) == 26
        assert len(labels) == len(features)
        assert any(l is not None for l in labels), "At least one window should have an anomaly label"


class TestTrain:
    def test_exits_early_when_no_data(self, tmp_path):
        with patch("backend.src.anomaly_detection.ml.train.load_windows", return_value=([], [])):
            with patch("backend.src.anomaly_detection.ml.train.ARTIFACT_DIR", tmp_path):
                with patch("backend.src.anomaly_detection.ml.train.mlflow"):
                    with patch("backend.src.anomaly_detection.ml.train.get_cursor"):
                        train()

        assert not (tmp_path / "isolation_forest.joblib").exists()
        assert not (tmp_path / "xgb_classifier.joblib").exists()

    def test_saves_all_three_artifacts(self, tmp_path):
        now = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

        fake_window = np.zeros(26, dtype=np.float32)
        rows = [
            dict(timestamp=now - timedelta(seconds=i * 10),
                 source="ATM_APP", atm_id="ATM-GB-0001",
                 metric_name="jvm_memory_used_bytes", metric_value=1e8,
                 event_type="ACTIVITY", severity="INFO",
                 raw_payload={}) for i in range(30)
        ]

        with patch("backend.src.anomaly_detection.ml.train.load_windows", return_value=([fake_window] * 10, [None] * 10)):
            with patch("backend.src.anomaly_detection.ml.train.ARTIFACT_DIR", tmp_path):
                with patch("backend.src.anomaly_detection.ml.train.mlflow"):
                    with patch("backend.src.anomaly_detection.ml.train.get_cursor"):
                        train()

        assert (tmp_path / "isolation_forest.joblib").exists()
        assert (tmp_path / "xgb_classifier.joblib").exists()
        assert (tmp_path / "label_encoder.joblib").exists()
        assert (tmp_path / "feature_names.json").exists()


class TestConstants:
    def test_window_seconds_is_300(self):
        assert WINDOW_SECONDS == 300

    def test_step_seconds_is_60(self):
        assert STEP_SECONDS == 60

    def test_if_contamination_is_010(self):
        assert IF_CONTAMINATION == 0.1

    def test_xgb_n_estimators_is_100(self):
        assert XGB_N_ESTIMATORS == 100

    def test_mlflow_experiment_name(self):
        assert MLFLOW_EXPERIMENT == "atm-anomaly-detection"

    def test_artifact_dir_in_backend_ml(self):
        assert "backend" in str(ARTIFACT_DIR) and "ml" in str(ARTIFACT_DIR)
        assert ARTIFACT_DIR.name == "artifacts"