"""Unit tests for ML training pipeline — mocks DB."""

from __future__ import annotations

import json
import numpy as np
import pytest
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
from sklearn.ensemble import IsolationForest


class _SpyIsolationForest(IsolationForest):
    """Records fit-set sizes; module-level so joblib.dump can pickle instances."""

    fit_sizes: list[int] = []

    def fit(self, X, y=None):
        type(self).fit_sizes.append(len(X))
        return super().fit(X, y)


class TestLoadOfflineDataset:
    def test_training_data_path_is_app_data(self):
        assert "training_data.json" in str(TRAINING_DATA)

    def test_offline_flag_is_false_by_default(self):
        assert USE_OFFLINE_DATA is False


class TestTemporalSplit:
    def test_monotonic_times_get_80_20_split(self):
        from backend.src.anomaly_detection.ml.train import _temporal_split

        base = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        times = [base + timedelta(minutes=i) for i in range(100)]
        train_mask, test_mask = _temporal_split(times)

        # Roughly 80/20: train = windows ending before the 80th-percentile
        # cutoff; holdout = windows starting at/after it. Windows straddling
        # the cutoff are excluded from BOTH masks (no shared rows), so
        # train + test may be < len(times).
        assert 70 <= train_mask.sum() <= 85
        assert 10 <= test_mask.sum() <= 25
        assert not np.any(train_mask & test_mask)
        # Every train window ends no later than every test window starts —
        # no row can appear in both splits.
        train_ts = [times[i] for i in range(100) if train_mask[i]]
        test_ts = [times[i] for i in range(100) if test_mask[i]]
        assert max(train_ts) + timedelta(seconds=WINDOW_SECONDS) <= min(test_ts)

    def test_straddling_windows_excluded_at_30s_step(self):
        # 30s-step start times as produced by _build_windows: consecutive
        # 60s windows overlap 50%, so windows near the cutoff straddle it.
        from backend.src.anomaly_detection.ml.train import _temporal_split

        base = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        times = [base + timedelta(seconds=30 * i) for i in range(200)]
        train_mask, test_mask = _temporal_split(times)

        assert not np.any(train_mask & test_mask)

        train_start = np.array(
            [times[i].timestamp() for i in range(200) if train_mask[i]]
        )
        test_start = np.array(
            [times[i].timestamp() for i in range(200) if test_mask[i]]
        )
        # No train window [t, t+60) shares rows with any test window.
        assert np.all(train_start[:, None] + WINDOW_SECONDS <= test_start[None, :])

        # Windows excluded from both splits sit strictly between the two
        # sides: they would overlap holdout rows if kept in train, and
        # train rows if kept in holdout.
        straddlers = np.array(
            [
                times[i].timestamp()
                for i in range(200)
                if not (train_mask[i] or test_mask[i])
            ]
        )
        assert len(straddlers) > 0
        assert np.all(straddlers > train_start.max())
        assert np.all(straddlers < test_start.min())
        assert train_mask.sum() + test_mask.sum() + len(straddlers) == len(times)

    def test_tied_timestamps_do_not_crash(self):
        from backend.src.anomaly_detection.ml.train import _temporal_split

        t = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        train_mask, test_mask = _temporal_split([t] * 10)
        assert train_mask.sum() + test_mask.sum() == 10

    def test_empty_times_returns_empty_masks(self):
        from backend.src.anomaly_detection.ml.train import _temporal_split

        train_mask, test_mask = _temporal_split([])
        assert len(train_mask) == 0 and len(test_mask) == 0


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


def _training_rows(n_points: int = 80) -> list[dict]:
    """Synthetic normal-only rows for one ATM (same shape as the full-train test)."""
    now = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    rows = []
    for i in range(n_points):
        t = now - timedelta(seconds=(n_points - i) * 10)
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
    return rows


class TestAtomicArtifactWrites:
    def test_atomic_dump_models_roundtrip(self, tmp_path):
        import joblib

        from backend.src.anomaly_detection.ml.train import _atomic_dump_models

        models = [
            ({"model": "xgb"}, tmp_path / "xgb_classifier.joblib"),
            ([1, 2, 3], tmp_path / "scaler.joblib"),
        ]
        _atomic_dump_models(models)

        assert joblib.load(tmp_path / "xgb_classifier.joblib") == {"model": "xgb"}
        assert joblib.load(tmp_path / "scaler.joblib") == [1, 2, 3]
        # No temp files left behind after a successful write.
        assert list(tmp_path.glob("*.tmp")) == []

    def test_atomic_dump_models_failure_is_clean(self, tmp_path):
        import joblib

        from backend.src.anomaly_detection.ml.train import _atomic_dump_models

        final = tmp_path / "scaler.joblib"
        joblib.dump({"previous": "model"}, final)
        before = final.read_bytes()

        with pytest.raises(Exception):
            _atomic_dump_models(
                [
                    ({"new": "model"}, final),  # dumps fine to temp
                    (lambda: None, tmp_path / "bad.joblib"),  # unpicklable → fails
                ]
            )

        # The previous artifact is untouched and no temp files leak.
        assert final.read_bytes() == before
        assert not (tmp_path / "bad.joblib").exists()
        assert list(tmp_path.glob("*.tmp")) == []

    def test_atomic_write_json_roundtrip(self, tmp_path):
        from backend.src.anomaly_detection.ml.train import _atomic_write_json

        _atomic_write_json(tmp_path / "if_unknown_threshold.json", {"threshold": -0.5})

        assert json.loads((tmp_path / "if_unknown_threshold.json").read_text()) == {
            "threshold": -0.5
        }
        assert list(tmp_path.glob("*.tmp")) == []


class TestOutOfSampleThresholdCalibration:
    def test_if_fit_and_calibrated_on_disjoint_subsets(self, tmp_path):
        import backend.src.anomaly_detection.ml.train as tr

        rows = _training_rows()

        calibration_calls: list[tuple[np.ndarray, np.ndarray]] = []
        real_calibrate = tr._calibrate_unknown_threshold

        def spy_calibrate(scores, y_true):
            calibration_calls.append((np.asarray(scores), np.asarray(y_true)))
            return real_calibrate(scores, y_true)

        _SpyIsolationForest.fit_sizes = []

        X_all, labels, _ = tr._build_windows(rows)
        n_windows = len(X_all)
        n_normal = sum(1 for lb in labels if lb is None)
        assert n_windows > 10  # sanity: the fixture must build enough windows

        mock_cur = MagicMock()
        mock_cur.__enter__ = MagicMock(return_value=mock_cur)
        mock_cur.__exit__ = MagicMock(return_value=None)
        mock_cur.fetchall.return_value = rows
        with patch("backend.src.anomaly_detection.ml.train.get_cursor") as mock_gc:
            mock_gc.return_value = mock_cur
            with patch("backend.src.anomaly_detection.ml.train.ARTIFACT_DIR", tmp_path):
                with patch("backend.src.anomaly_detection.ml.train.mlflow"):
                    with patch.object(tr, "IsolationForest", _SpyIsolationForest):
                        with patch.object(
                            tr, "_calibrate_unknown_threshold", spy_calibrate
                        ):

                            def noop_alias(*args, **kwargs):
                                pass

                            mock_client = MagicMock()
                            mock_client.set_registered_model_alias = noop_alias
                            with patch(
                                "mlflow.tracking.MlflowClient",
                                return_value=mock_client,
                            ):
                                tr.train()

        # Threshold is calibrated exactly once, on a held-out subset —
        # strictly fewer windows than the full dataset.
        assert len(calibration_calls) == 1
        calib_scores, calib_y = calibration_calls[0]
        assert 0 < len(calib_scores) < n_windows

        # The final IF fit (last recorded fit) uses fewer than all normal
        # windows — the calibration subset is never fit on.
        assert _SpyIsolationForest.fit_sizes[-1] < n_normal

        # The shipped threshold artifact reflects the calibrated value.
        threshold = json.loads((tmp_path / "if_unknown_threshold.json").read_text())[
            "threshold"
        ]
        assert isinstance(threshold, float)
