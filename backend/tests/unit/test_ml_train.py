"""Unit tests for ML training pipeline — mocks DB."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch


from backend.src.anomaly_detection.ml.train import (
    train,
    WINDOW_SECONDS,
    STEP_SECONDS,
    IF_CONTAMINATION,
    XGB_N_ESTIMATORS,
    MLFLOW_EXPERIMENT,
    ARTIFACT_DIR,
    USE_OFFLINE_DATA,
    TRAINING_DATA,
)


class TestLoadOfflineDataset:
    def test_training_data_path_is_app_data(self):
        assert "training_data.json" in str(TRAINING_DATA)

    def test_offline_flag_is_false_by_default(self):
        assert USE_OFFLINE_DATA is False


class TestTrain:
    def test_exits_early_when_no_data(self, tmp_path):
        with patch("backend.src.anomaly_detection.ml.train.get_cursor") as mock_gc:
            mock_cur = MagicMock()
            mock_cur.__enter__ = MagicMock(return_value=mock_cur)
            mock_cur.__exit__ = MagicMock(return_value=None)
            mock_cur.fetchall.return_value = []
            mock_gc.return_value = mock_cur
            with patch("backend.src.anomaly_detection.ml.train.ARTIFACT_DIR", tmp_path):
                with patch("backend.src.anomaly_detection.ml.train.mlflow"):
                    train()

        assert not (tmp_path / "isolation_forest.joblib").exists()
        assert not (tmp_path / "xgb_classifier.joblib").exists()

    def test_saves_all_artifacts(self, tmp_path):
        now = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

        rows = []
        for i in range(120):
            t = now - timedelta(seconds=(120 - i) * 10)
            rows.extend(
                [
                    dict(
                        timestamp=t,
                        source="PROMETHEUS",
                        atm_id="ATM-GB-0001",
                        metric_name="jvm_memory_used_bytes",
                        metric_value=8e7 + i * 1e6,
                        event_type=None,
                        severity=None,
                        raw_payload={},
                    ),
                    dict(
                        timestamp=t,
                        source="PROMETHEUS",
                        atm_id="ATM-GB-0001",
                        metric_name="jvm_gc_pause_seconds_sum",
                        metric_value=0.1,
                        event_type=None,
                        severity=None,
                        raw_payload={},
                    ),
                    dict(
                        timestamp=t,
                        source="PROMETHEUS",
                        atm_id="ATM-GB-0001",
                        metric_name="process_cpu_usage",
                        metric_value=0.3,
                        event_type=None,
                        severity=None,
                        raw_payload={},
                    ),
                    dict(
                        timestamp=t,
                        source="CLOUD",
                        atm_id="ATM-GB-0001",
                        metric_name="container/cpu/usage_time",
                        metric_value=30.0,
                        event_type=None,
                        severity=None,
                        raw_payload={},
                    ),
                    dict(
                        timestamp=t,
                        source="OS",
                        atm_id="ATM-GB-0001",
                        metric_name="windows_os_snapshot",
                        metric_value=50.0,
                        event_type=None,
                        severity=None,
                        raw_payload={},
                    ),
                    dict(
                        timestamp=t,
                        source="KAFKA",
                        atm_id="ATM-GB-0001",
                        metric_name=None,
                        metric_value=None,
                        event_type="METRIC",
                        severity="INFO",
                        raw_payload=json.dumps(
                            {
                                "response_time_ms": 150.0,
                                "transaction_success_rate": 98.0,
                            }
                        ),
                    ),
                    dict(
                        timestamp=t,
                        source="ATM_APP",
                        atm_id="ATM-GB-0001",
                        metric_name=None,
                        metric_value=None,
                        event_type="HEARTBEAT",
                        severity="INFO",
                        raw_payload={},
                    ),
                ]
            )

        with patch("backend.src.anomaly_detection.ml.train.get_cursor") as mock_gc:
            mock_cur = MagicMock()
            mock_cur.__enter__ = MagicMock(return_value=mock_cur)
            mock_cur.__exit__ = MagicMock(return_value=None)
            mock_cur.fetchall.return_value = rows
            mock_gc.return_value = mock_cur
            with patch("backend.src.anomaly_detection.ml.train.ARTIFACT_DIR", tmp_path):
                with patch("backend.src.anomaly_detection.ml.train.mlflow"):

                    def noop_alias(*args, **kwargs):
                        pass

                    mock_client = MagicMock()
                    mock_client.set_registered_model_alias = noop_alias
                    with patch(
                        "mlflow.tracking.MlflowClient", return_value=mock_client
                    ):
                        train()

        assert (tmp_path / "isolation_forest.joblib").exists()
        assert (tmp_path / "xgb_classifier.joblib").exists()
        assert (tmp_path / "label_encoder.joblib").exists()
        assert (tmp_path / "feature_names.json").exists()
        assert (tmp_path / "if_feature_indices.json").exists()
        assert (tmp_path / "if_unknown_threshold.json").exists()
        assert (tmp_path / "scaler.joblib").exists()


class TestConstants:
    def test_window_seconds_is_60(self):
        assert WINDOW_SECONDS == 60

    def test_step_seconds_is_30(self):
        assert STEP_SECONDS == 30

    def test_if_contamination_is_010(self):
        assert IF_CONTAMINATION == 0.1

    def test_xgb_n_estimators_is_100(self):
        assert XGB_N_ESTIMATORS == 100

    def test_mlflow_experiment_name(self):
        assert MLFLOW_EXPERIMENT == "atm-anomaly-detection"

    def test_artifact_dir_in_backend_ml(self):
        assert "backend" in str(ARTIFACT_DIR) and "ml" in str(ARTIFACT_DIR)
        assert ARTIFACT_DIR.name == "artifacts"
