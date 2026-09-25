"""Tests for eval_external.py — tiny fitted models in tmp_path."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import joblib
import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import LabelEncoder, StandardScaler
from xgboost import XGBClassifier

from backend.src.anomaly_detection.ml.feature_engineering import FEATURE_COUNT

_NOW = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


def _build_rows() -> list[dict]:
    """120 PROMETHEUS rows, 1 ATM, 10s apart; every 12th row tagged A3."""
    rows = []
    for i in range(120):
        t = _NOW - timedelta(seconds=(120 - i) * 10)
        row = dict(
            timestamp=t.isoformat(),
            source="PROMETHEUS",
            atm_id="ATM-GB-0001",
            event_type=None,
            severity=None,
            transaction_id=None,
            raw_payload={},
            correlation_id=None,
            metric_name="jvm_memory_used_bytes",
            metric_value=1_000_000 + i * 100,
        )
        if i % 12 == 0:
            row["raw_payload"] = {"_anomaly_tag": "A3_HIGH_LATENCY"}
        rows.append(row)
    return rows


def _fit_models(model_dir: Path) -> None:
    """Fit tiny real models and write the artifact files eval_external reads."""
    X = np.random.default_rng(0).random((40, FEATURE_COUNT))
    y = np.array([0] * 30 + [1] * 10)

    clf = XGBClassifier(n_estimators=5, max_depth=2, random_state=0)
    clf.fit(X, y)
    joblib.dump(clf, model_dir / "xgb_classifier.joblib")

    le = LabelEncoder()
    le.fit(["A3", "NORMAL"])
    joblib.dump(le, model_dir / "label_encoder.joblib")

    scaler = StandardScaler()
    scaler.fit(X)
    joblib.dump(scaler, model_dir / "scaler.joblib")

    iso = IsolationForest(n_estimators=10, random_state=0)
    iso.fit(scaler.transform(X))
    joblib.dump(iso, model_dir / "isolation_forest.joblib")

    with open(model_dir / "if_feature_indices.json", "w") as f:
        json.dump(list(range(FEATURE_COUNT)), f)
    with open(model_dir / "if_unknown_threshold.json", "w") as f:
        json.dump({"threshold": -0.1}, f)


class TestEvalExternal:
    def test_evaluates_external_dataset_read_only(self, tmp_path, capsys):
        import backend.src.anomaly_detection.ml.eval_external as ee

        model_dir = tmp_path / "artifacts"
        model_dir.mkdir()
        _fit_models(model_dir)
        before = sorted(p.name for p in model_dir.iterdir())

        eval_json = tmp_path / "eval_data.json"
        with open(eval_json, "w") as f:
            json.dump(_build_rows(), f)

        with patch.object(ee, "ARTIFACT_DIR", model_dir):
            with patch.dict("os.environ", {"EVAL_DATA_PATH": str(eval_json)}):
                ee.main()

        out = capsys.readouterr().out
        assert "macro-F1" in out
        assert "Config-B IF" in out
        after = sorted(p.name for p in model_dir.iterdir())
        assert after == before

    def test_missing_eval_data_path_exits(self, capsys):
        import backend.src.anomaly_detection.ml.eval_external as ee

        with patch.dict("os.environ", {}, clear=False):
            try:
                ee.main()
            except SystemExit as e:
                assert "EVAL_DATA_PATH" in str(e)
            else:
                raise AssertionError("expected SystemExit")
