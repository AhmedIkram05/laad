"""Evaluate champion artifacts on an external dataset (generator config B).

Usage:
    EVAL_DATA_PATH=/tmp/laad_eval_configB.json PYTHONPATH=. \
        .venv/bin/python -m backend.src.anomaly_detection.ml.eval_external

Set EVAL_LOG_MLFLOW=true (with MLFLOW_TRACKING_URI) to log xgb_external_* metrics.
Never writes to ARTIFACT_DIR; never registers models or touches aliases.
"""

import json
import os
from pathlib import Path

import joblib
import numpy as np
from sklearn.metrics import (
    average_precision_score,
    balanced_accuracy_score,
    classification_report,
    f1_score,
    roc_auc_score,
)

from backend.src.anomaly_detection.ml.train import (
    ARTIFACT_DIR,
    _build_windows,
    load_offline_dataset,
)


def main() -> None:
    eval_path = os.getenv("EVAL_DATA_PATH")
    if not eval_path:
        raise SystemExit("Set EVAL_DATA_PATH to the external dataset JSON")

    rows = load_offline_dataset(Path(eval_path))
    X, labels, _ = _build_windows(rows)
    if X.shape[0] == 0:
        raise SystemExit("No valid windows in external dataset")

    clf = joblib.load(ARTIFACT_DIR / "xgb_classifier.joblib")
    le = joblib.load(ARTIFACT_DIR / "label_encoder.joblib")
    y_true = le.transform([lb if lb is not None else "NORMAL" for lb in labels])
    y_pred = clf.predict(X)
    print(
        classification_report(
            y_true,
            y_pred,
            labels=range(len(le.classes_)),
            target_names=le.classes_,
            zero_division=0,
        )
    )
    macro_f1 = float(f1_score(y_true, y_pred, average="macro"))
    bacc = float(balanced_accuracy_score(y_true, y_pred))
    print(f"Config-B XGBoost macro-F1: {macro_f1:.3f} · balanced acc: {bacc:.3f} · n={len(labels)}")

    scaler = joblib.load(ARTIFACT_DIR / "scaler.joblib")
    with open(ARTIFACT_DIR / "if_feature_indices.json") as f:
        idx = json.load(f)
    iso = joblib.load(ARTIFACT_DIR / "isolation_forest.joblib")
    with open(ARTIFACT_DIR / "if_unknown_threshold.json") as f:
        threshold = float(json.load(f)["threshold"])
    scores = iso.score_samples(scaler.transform(X)[:, idx])
    y_bin = np.array([lb is not None for lb in labels], dtype=int)
    pred_bin = (scores < threshold).astype(int)
    if_precision = float(np.mean(pred_bin == y_bin))
    pr_auc = float(average_precision_score(y_bin, -scores))
    auc = float(roc_auc_score(y_bin, -scores))
    print(f"Config-B IF: precision={if_precision:.3f} PR-AUC={pr_auc:.4f} AUC={auc:.4f}")

    if os.getenv("EVAL_LOG_MLFLOW", "").lower() == "true":
        import mlflow

        mlflow.set_tracking_uri(os.environ["MLFLOW_TRACKING_URI"])
        mlflow.set_experiment("atm-anomaly-detection")
        with mlflow.start_run(run_name="external_eval_config_B"):
            mlflow.log_metric("xgb_external_macro_f1", macro_f1)
            mlflow.log_metric("xgb_external_balanced_accuracy", bacc)
            mlflow.log_metric("if_external_pr_auc", pr_auc)
            mlflow.log_metric("if_external_auc", auc)
            mlflow.log_metric("if_external_precision", if_precision)


if __name__ == "__main__":
    main()
