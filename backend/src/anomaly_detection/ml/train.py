"""Training pipeline for the ML anomaly detector.

Steps:
    1. Query v_unified_analysis from PostgreSQL, split into NON-overlapping windows
    2. Extract features and labels per window
    3. Train Isolation Forest on normal windows only
    4. Train XGBoost on all labelled windows (normal + anomaly types) with class balancing
    5. Log parameters, metrics, and model artifacts to MLflow
    6. Save models to ml/artifacts/

Usage:
    python -m backend.src.anomaly_detection.ml.train
"""
from __future__ import annotations

import json
import os
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

import xgboost as xgb
import mlflow
import mlflow.sklearn
import mlflow.xgboost
import numpy as np
import pandas as pd
import joblib
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import LabelEncoder
from sklearn.model_selection import StratifiedKFold, cross_val_score
from sklearn.metrics import classification_report
from collections import Counter

from backend.src.database.connection import get_cursor
from backend.src.anomaly_detection.ml.feature_engineering import extract_features, extract_label, FEATURE_NAMES, FEATURE_COUNT

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)

ARTIFACT_DIR    = Path(__file__).parent / "artifacts"
WINDOW_SECONDS  = 600
STEP_SECONDS    = WINDOW_SECONDS
IF_CONTAMINATION = 0.1
XGB_N_ESTIMATORS = 100
MLFLOW_EXPERIMENT = "atm-anomaly-detection"

_tracking_uri = os.environ.get("MLFLOW_TRACKING_URI", "http://mlflow:5000")


def load_windows(minutes: int = 60) -> tuple[list[np.ndarray], list[str | None]]:
    """Query recent DB rows and split into NON-overlapping windows.

    Uses step=WINDOW_SECONDS to avoid the same anomaly appearing in multiple windows,
    which would inflate training metrics and cause overfitting.

    Args:
        minutes: how far back to query (default 60 min)

    Returns:
        Tuple of (features list, labels list)
    """
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT timestamp, source, atm_id, metric_name, metric_value,
                   event_type, severity, raw_payload
            FROM v_unified_analysis
            WHERE timestamp >= %s
            ORDER BY timestamp ASC
            """,
            (cutoff,)
        )
        rows = [dict(r) for r in cur.fetchall()]

    if not rows:
        log.warning("No rows returned from v_unified_analysis in last %d minutes", minutes)
        return [], []

    start = rows[0]["timestamp"]
    end   = rows[-1]["timestamp"]
    window_delta = timedelta(seconds=WINDOW_SECONDS)
    step_delta   = timedelta(seconds=STEP_SECONDS)

    features: list[np.ndarray] = []
    labels:   list[str | None] = []

    t = start
    while t + window_delta <= end:
        window_rows = [r for r in rows if t <= r["timestamp"] < t + window_delta]
        if len(window_rows) >= 5:
            feats = extract_features(window_rows)
            if len(feats) == FEATURE_COUNT:
                features.append(feats)
                labels.append(extract_label(window_rows))
        t += step_delta

    return features, labels


def train() -> None:
    """Run the full training pipeline."""
    ARTIFACT_DIR.mkdir(exist_ok=True)

    mlflow.set_tracking_uri(_tracking_uri)
    mlflow.set_experiment(MLFLOW_EXPERIMENT)
    with mlflow.start_run(run_name="isolation_forest_xgboost"):
        mlflow.log_params({
            "window_seconds":    WINDOW_SECONDS,
            "step_seconds":       STEP_SECONDS,
            "overlapping":        False,
            "if_contamination":  IF_CONTAMINATION,
            "xgb_n_estimators":  XGB_N_ESTIMATORS,
            "n_features":        FEATURE_COUNT,
        })

        X_list, labels = load_windows(minutes=360)

        if not X_list:
            log.error("No training data found. Ensure the generator has been running.")
            return

        X_all = np.stack(X_list)
        label_counts = {l: labels.count(l) for l in set(labels)}
        print(f"Loaded {len(X_all)} non-overlapping windows. Label distribution: {label_counts}")

        normal_mask = np.array([l is None for l in labels])
        X_normal    = X_all[normal_mask]

        if len(X_normal) < 10:
            log.warning("Very few normal windows (%d) — training may be unreliable. "
                        "Normal windows should accumulate after ~15 min of generator running. "
                        "Consider re-running training after more normal data is generated.", len(X_normal))
            if len(X_normal) == 0:
                log.error("No normal windows available. Isolation Forest requires at least some normal samples.")
                return

        print(f"Training Isolation Forest on {len(X_normal)} normal windows...")
        iso_forest = IsolationForest(
            n_estimators=200,
            contamination=IF_CONTAMINATION,
            random_state=42,
            n_jobs=-1,
        )
        iso_forest.fit(X_normal)

        if_scores = iso_forest.predict(X_all)
        if_precision = float(np.mean([
            (if_scores[i] == -1) == (labels[i] is not None)
            for i in range(len(labels))
        ]))
        mlflow.log_metric("if_anomaly_precision", if_precision)
        print(f"Isolation Forest anomaly detection precision: {if_precision:.3f}")

        joblib.dump(iso_forest, ARTIFACT_DIR / "isolation_forest.joblib")
        mlflow.sklearn.log_model(iso_forest, "isolation_forest")
        mlflow.log_artifact(str(ARTIFACT_DIR / "isolation_forest.joblib"))

        label_strings = [l if l is not None else "NORMAL" for l in labels]
        le = LabelEncoder()
        y  = le.fit_transform(label_strings)

        class_counts = Counter(label_strings)
        normal_count = class_counts.get("NORMAL", 1)
        sample_weights = np.array([
            normal_count / max(class_counts.get(lb, 1), 1)
            for lb in label_strings
        ])

        print(f"Training XGBoost classifier on {len(X_all)} windows (class-balanced)...")
        clf = xgb.XGBClassifier(
            n_estimators=XGB_N_ESTIMATORS,
            max_depth=6,
            learning_rate=0.1,
            subsample=0.8,
            colsample_bytree=0.8,
            eval_metric="mlogloss",
            random_state=42,
            n_jobs=-1,
        )
        clf.fit(X_all, y, sample_weight=sample_weights)

        cv_n_splits = min(5, min(class_counts.values()))
        if cv_n_splits < 2:
            log.warning("Not enough samples per class for CV. Skipping cross-validation.")
            cv_scores = np.array([np.nan])
        else:
            cv = StratifiedKFold(n_splits=cv_n_splits, shuffle=True, random_state=42)
            cv_scores = cross_val_score(clf, X_all, y, cv=cv, scoring="accuracy", n_jobs=-1)

        cv_mean = float(cv_scores.mean()) if not np.isnan(cv_scores.mean()) else 0.0
        cv_std = float(cv_scores.std()) if not np.isnan(cv_scores.std()) else 0.0
        mlflow.log_metric("xgb_cv_accuracy_mean", cv_mean)
        mlflow.log_metric("xgb_cv_accuracy_std",  cv_std)
        print(f"XGBoost CV accuracy: {cv_mean:.3f} ± {cv_std:.3f}")

        y_pred = clf.predict(X_all)
        report = classification_report(y, y_pred, target_names=le.classes_, output_dict=True, zero_division=0)
        for cls, metrics in report.items():
            if isinstance(metrics, dict):
                for metric, val in metrics.items():
                    if not np.isnan(float(val)):
                        mlflow.log_metric(f"xgb_{cls}_{metric}".replace(" ", "_"), float(val))

        joblib.dump(clf, ARTIFACT_DIR / "xgb_classifier.joblib")
        joblib.dump(le,  ARTIFACT_DIR / "label_encoder.joblib")
        mlflow.xgboost.log_model(clf, "xgb_classifier")
        mlflow.log_artifact(str(ARTIFACT_DIR / "xgb_classifier.joblib"))
        mlflow.log_artifact(str(ARTIFACT_DIR / "label_encoder.joblib"))

        with open(ARTIFACT_DIR / "feature_names.json", "w") as f:
            json.dump(FEATURE_NAMES, f)
        mlflow.log_artifact(str(ARTIFACT_DIR / "feature_names.json"))

        feat_imp = pd.Series(clf.feature_importances_, index=FEATURE_NAMES).sort_values(ascending=False)
        print("Top 10 features by importance:")
        for feat, imp in feat_imp.head(10).items():
            print(f"  {feat}: {imp:.4f}")
            mlflow.log_metric(f"feat_importance_{feat}", float(imp))

        print(f"Training complete. Artifacts saved to {ARTIFACT_DIR}")


if __name__ == "__main__":
    train()