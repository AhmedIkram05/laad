"""Training pipeline for the ML anomaly detector.

Steps:
    1. Query v_unified_analysis from PostgreSQL, split into NON-overlapping windows
    2. Extract features and labels per window
    3. Train XGBoost on all labelled windows (normal + anomaly types) with class balancing
    4. Select top-K features from XGBoost feature importance for Isolation Forest
    5. Grid-search IF hyperparameters on held-out validation split
    6. Train Isolation Forest on normal windows only (selected features)
    7. Calibrate UNKNOWN anomaly threshold via Youden's J statistic
    8. Log parameters, metrics, and model artifacts to MLflow
    9. Save models to ml/artifacts/

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
from sklearn.preprocessing import LabelEncoder, StandardScaler
from sklearn.model_selection import StratifiedKFold, cross_val_score, train_test_split
from sklearn.metrics import classification_report, roc_auc_score
from collections import Counter

from backend.src.database.connection import get_cursor
from backend.src.anomaly_detection.ml.feature_engineering import extract_features, extract_label, FEATURE_NAMES, FEATURE_COUNT

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)

ARTIFACT_DIR    = Path(__file__).parent / "artifacts"
TRAINING_DATA   = Path(os.getenv("TRAINING_DATA_PATH", "/app/data/training_data.json"))
WINDOW_SECONDS  = 60
STEP_SECONDS    = 30
IF_CONTAMINATION = 0.1
XGB_N_ESTIMATORS = 100
MLFLOW_EXPERIMENT = "atm-anomaly-detection"
USE_OFFLINE_DATA  = os.getenv("USE_OFFLINE_DATA", "false").lower() == "true"
XGB_MODEL_NAME    = "atm-xgb-classifier"
IF_MODEL_NAME     = "atm-isolation-forest"
MLFLOW_TRACKING_URI = os.environ.get("MLFLOW_TRACKING_URI", "http://mlflow:5000")
IF_FEATURE_SELECTION_K = 20


def load_offline_dataset() -> list[dict]:
    """Load the pre-generated training dataset from disk."""
    if not TRAINING_DATA.exists():
        log.warning("Offline training dataset not found at %s — skipping", TRAINING_DATA)
        return []
    with open(TRAINING_DATA) as f:
        rows = [{"timestamp": datetime.fromisoformat(r["timestamp"].replace("Z", "+00:00")), **{k: v for k, v in r.items() if k != "timestamp"}}
                for r in json.load(f)]
    log.info("Loaded %d offline training rows from %s", len(rows), TRAINING_DATA)
    return rows


def _grid_search_if(
    X_normal_tr: np.ndarray,
    X_normal_val: np.ndarray,
    X_anomaly_val: np.ndarray,
) -> dict:
    """Sequential 1D grid search for Isolation Forest hyperparameters.

    Evaluates by AUC-ROC of score_samples() on a combined validation set
    (normal + anomalous windows). Contamination is swept for completeness
    but does not affect score_samples() output.

    Args:
        X_normal_tr: Scaled normal windows for training.
        X_normal_val: Scaled normal windows for validation.
        X_anomaly_val: Scaled anomalous windows for validation (can be empty).

    Returns:
        Dict of best hyperparameters.
    """
    y_val = np.array([0] * len(X_normal_val) + [1] * len(X_anomaly_val))
    X_val = np.vstack([X_normal_val, X_anomaly_val]) if len(X_anomaly_val) > 0 else X_normal_val
    if len(y_val) == 0:
        log.warning("No validation data for grid search — using default params")
        return {}
    if len(np.unique(y_val)) < 2:
        log.warning("Only one class in validation data (need both normal + anomaly) — using default params")
        return {}

    best_params: dict = {}
    best_auc = -1.0
    param_sweeps = [
        ("max_features", [0.1, 0.3, 0.5, 0.7, 1.0]),
        ("contamination", ["auto", 0.01, 0.02, 0.05, 0.1]),
        ("max_samples", ["auto", 0.3, 0.5, 0.7]),
    ]

    fixed = {"n_estimators": 200, "random_state": 42, "n_jobs": -1, "bootstrap": True}

    for param_name, values in param_sweeps:
        best_param_val = None
        best_param_auc = -1.0
        for val in values:
            params = {**fixed, **best_params, param_name: val}
            try:
                iso = IsolationForest(**params)
                iso.fit(X_normal_tr)
                scores = iso.score_samples(X_val)
                auc = roc_auc_score(y_val, -scores)
            except Exception:
                continue
            log.info("  IF grid %s=%s → AUC-ROC=%.4f", param_name, val, auc)
            mlflow.log_metric(f"if_grid_{param_name}_{val}", auc, step=1)
            if auc > best_param_auc:
                best_param_auc = auc
                best_param_val = val
        if best_param_val is not None:
            best_params[param_name] = best_param_val
            if best_param_auc > best_auc:
                best_auc = best_param_auc
            log.info("  Best %s=%s (AUC=%.4f)", param_name, best_param_val, best_param_auc)

    log.info("Grid search complete: best params=%s (AUC=%.4f)", best_params, best_auc)
    mlflow.log_metric("if_grid_best_auc", best_auc)
    for k, v in best_params.items():
        mlflow.log_param(f"if_best_{k}", v)
    return best_params


def _calibrate_unknown_threshold(
    scores: np.ndarray,
    y_true: np.ndarray,
) -> float:
    """Find IF score threshold maximising F1 for anomaly detection.

    Sweeps 200 thresholds across the score range, computes precision/recall/
    F1 at each point, and returns the threshold with the highest F1.
    Anomalous windows have y_true=1 and produce more negative IF scores.
    """
    thresholds = np.linspace(scores.min(), scores.max(), 200)
    best_f1 = -1.0
    best_threshold = -0.75

    for thresh in thresholds:
        y_pred = (scores < thresh).astype(int)
        tp = int(np.sum((y_pred == 1) & (y_true == 1)))
        fp = int(np.sum((y_pred == 1) & (y_true == 0)))
        fn = int(np.sum((y_pred == 0) & (y_true == 1)))
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
        if f1 > best_f1:
            best_f1 = f1
            best_threshold = float(thresh)

    log.info("Threshold calibration: best_threshold=%.4f (F1=%.4f)", best_threshold, best_f1)
    mlflow.log_metric("if_best_f1", best_f1)
    mlflow.log_metric("if_unknown_threshold", best_threshold)
    return best_threshold


def train() -> None:
    """Run the full training pipeline."""
    import subprocess

    ARTIFACT_DIR.mkdir(exist_ok=True)

    git_sha = os.getenv("GIT_COMMIT_SHA", "").strip()[:8]
    if not git_sha:
        try:
            git_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL).decode().strip()[:8]
        except Exception:
            git_sha = "unknown"

    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    mlflow.set_experiment(MLFLOW_EXPERIMENT)
    with mlflow.start_run(run_name="isolation_forest_xgboost"):
        mlflow.set_tag("git_sha", git_sha)
        mlflow.log_params({
            "window_seconds":    WINDOW_SECONDS,
            "step_seconds":       STEP_SECONDS,
            "overlapping":        False,
            "if_contamination":  IF_CONTAMINATION,
            "xgb_n_estimators":  XGB_N_ESTIMATORS,
            "n_features":        FEATURE_COUNT,
            "use_offline_data":  USE_OFFLINE_DATA,
            "if_feature_selection_k": IF_FEATURE_SELECTION_K,
            "random_state": 42,
        })

        if USE_OFFLINE_DATA:
            all_rows = load_offline_dataset()
            if all_rows:
                log.info("Using %d offline rows for training", len(all_rows))
            else:
                cutoff = datetime.now(timezone.utc) - timedelta(minutes=360)
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
                    all_rows = [dict(r) for r in cur.fetchall()]
                log.info("Fell back to %d live rows from DB", len(all_rows))
        else:
            cutoff = datetime.now(timezone.utc) - timedelta(minutes=360)
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
                all_rows = [dict(r) for r in cur.fetchall()]
            log.info("Loaded %d live rows from DB", len(all_rows))

        if not all_rows:
            log.error("No training data found. Ensure the generator has been running.")
            return

        start_ts = all_rows[0]["timestamp"]
        end_ts   = all_rows[-1]["timestamp"]
        window_delta = timedelta(seconds=WINDOW_SECONDS)
        step_delta   = timedelta(seconds=STEP_SECONDS)

        atm_groups: dict[str | None, list[dict]] = {}
        for r in all_rows:
            key = r.get("atm_id")
            atm_groups.setdefault(key, []).append(r)

        X_list: list[np.ndarray] = []
        labels: list[str | None] = []

        for entity_id, entity_rows in atm_groups.items():
            if len(entity_rows) < 5:
                continue
            entity_rows.sort(key=lambda r: r["timestamp"])
            e_start = entity_rows[0]["timestamp"]
            e_end = entity_rows[-1]["timestamp"]
            t = e_start
            while t + window_delta <= e_end + timedelta(seconds=1):
                window_rows = [r for r in entity_rows if t <= r["timestamp"] < t + window_delta]
                if len(window_rows) >= 5:
                    feats = extract_features(window_rows)
                    if len(feats) == FEATURE_COUNT:
                        X_list.append(feats)
                        labels.append(extract_label(window_rows))
                t += step_delta

        if not X_list:
            log.error("No valid windows (need >=5 rows per window). Check feature engineering.")
            return

        X_all = np.stack(X_list)
        label_counts = {str(l): labels.count(l) for l in set(labels) if l is not None}
        label_counts["NORMAL"] = labels.count(None)
        print(f"Loaded {len(X_all)} non-overlapping windows. Label distribution: {label_counts}")

        normal_mask = np.array([l is None for l in labels])
        X_normal = X_all[normal_mask]
        X_anomaly = X_all[~normal_mask]

        if len(X_normal) < 10:
            log.warning("Very few normal windows (%d) — training may be unreliable. "
                        "Normal windows should accumulate after ~15 min of generator running. "
                        "Consider re-running training after more normal data is generated.", len(X_normal))
            if len(X_normal) == 0:
                log.error("No normal windows available. Isolation Forest requires at least some normal samples.")
                return

        # ─────────────────────────────────────────────────────────────────────
        # XGBoost training — runs first so we can use its feature importance
        # for IF feature selection.
        # ─────────────────────────────────────────────────────────────────────
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

        # ─────────────────────────────────────────────────────────────────────
        # Feature selection for IF — use top-K features from XGBoost importance
        # ─────────────────────────────────────────────────────────────────────
        importance = clf.feature_importances_
        sorted_idx = np.argsort(importance)[::-1]
        nonzero = int(np.sum(importance > 0))
        k = min(max(IF_FEATURE_SELECTION_K, nonzero), FEATURE_COUNT)
        if_feature_indices = sorted(sorted_idx[:k].tolist())
        if_feature_names = [FEATURE_NAMES[i] for i in if_feature_indices]

        with open(ARTIFACT_DIR / "if_feature_indices.json", "w") as f:
            json.dump(if_feature_indices, f)
        mlflow.log_artifact(str(ARTIFACT_DIR / "if_feature_indices.json"))

        print(f"Selected {len(if_feature_indices)} features for IF:")
        for name, idx in zip(if_feature_names, if_feature_indices):
            imp = float(importance[idx])
            print(f"  [{idx}] {name}: {imp:.4f}")
            mlflow.log_metric(f"if_selected_feature_{name}", imp)

        # ─────────────────────────────────────────────────────────────────────
        # Isolation Forest training with grid search and threshold calibration
        # ─────────────────────────────────────────────────────────────────────
        # Fit scaler on ALL 49 features (inference pipeline scales before subsetting)
        scaler = StandardScaler()
        scaler.fit(X_normal)

        X_all_if = X_all[:, if_feature_indices]
        X_normal_if = X_all_if[normal_mask]
        X_anomaly_if = X_all_if[~normal_mask]

        X_normal_scaled = scaler.transform(X_normal)
        X_normal_scaled_if = X_normal_scaled[:, if_feature_indices]
        X_anomaly_scaled = scaler.transform(X_anomaly) if len(X_anomaly) > 0 else np.array([]).reshape(0, FEATURE_COUNT)
        X_anomaly_scaled_if = X_anomaly_scaled[:, if_feature_indices] if len(X_anomaly_scaled) > 0 else np.array([]).reshape(0, len(if_feature_indices))

        # Grid search: split normal windows into train/val, evaluate on val+anomaly
        X_normal_tr, X_normal_val = train_test_split(
            X_normal_scaled_if, test_size=0.2, random_state=42
        )
        log.info("IF grid search: %d train / %d val normal + %d anomaly windows",
                 len(X_normal_tr), len(X_normal_val), len(X_anomaly_scaled_if))

        best_if_params = _grid_search_if(X_normal_tr, X_normal_val, X_anomaly_scaled_if)

        # Train final IF on ALL normal windows with best params
        final_params = {
            "n_estimators": 200,
            "random_state": 42,
            "n_jobs": -1,
            "bootstrap": True,
            **best_if_params,
        }
        print(f"Training final Isolation Forest on {len(X_normal_scaled_if)} normal windows...")
        log.info("Final IF params: %s", final_params)
        iso_forest = IsolationForest(**final_params)
        iso_forest.fit(X_normal_scaled_if)

        # Evaluate IF anomaly detection precision on all windows
        X_all_scaled = scaler.transform(X_all)
        X_all_scaled_if = X_all_scaled[:, if_feature_indices]
        if_scores = iso_forest.predict(X_all_scaled_if)
        if_precision = float(np.mean([
            (if_scores[i] == -1) == (labels[i] is not None)
            for i in range(len(labels))
        ]))
        mlflow.log_metric("if_anomaly_precision", if_precision)
        print(f"Isolation Forest anomaly detection precision: {if_precision:.3f}")

        # Calibrate UNKNOWN anomaly threshold via Youden's J
        all_if_density_scores = iso_forest.score_samples(X_all_scaled_if)
        y_anomaly_binary = (~normal_mask).astype(int)
        unknown_threshold = _calibrate_unknown_threshold(all_if_density_scores, y_anomaly_binary)

        with open(ARTIFACT_DIR / "if_unknown_threshold.json", "w") as f:
            json.dump({"threshold": unknown_threshold}, f)
        mlflow.log_artifact(str(ARTIFACT_DIR / "if_unknown_threshold.json"))

        # ─────────────────────────────────────────────────────────────────────
        # MLflow model registry — log_model BEFORE additional metric logging
        # to avoid UNIQUE constraint conflicts (MLflow v3.1.1 re-logs
        # existing run metrics internally).
        # ─────────────────────────────────────────────────────────────────────
        xgb_uri = mlflow.xgboost.log_model(clf, "xgb_classifier")
        if_uri  = mlflow.sklearn.log_model(iso_forest, "isolation_forest")

        # ─────────────────────────────────────────────────────────────────────
        # Log remaining metrics and save artifacts
        # ─────────────────────────────────────────────────────────────────────
        joblib.dump(clf, ARTIFACT_DIR / "xgb_classifier.joblib")
        joblib.dump(le,  ARTIFACT_DIR / "label_encoder.joblib")
        mlflow.log_artifact(str(ARTIFACT_DIR / "xgb_classifier.joblib"))
        mlflow.log_artifact(str(ARTIFACT_DIR / "label_encoder.joblib"))

        joblib.dump(iso_forest, ARTIFACT_DIR / "isolation_forest.joblib")
        joblib.dump(scaler, ARTIFACT_DIR / "scaler.joblib")
        mlflow.log_artifact(str(ARTIFACT_DIR / "isolation_forest.joblib"))
        mlflow.log_artifact(str(ARTIFACT_DIR / "scaler.joblib"))

        with open(ARTIFACT_DIR / "feature_names.json", "w") as f:
            json.dump(FEATURE_NAMES, f)
        mlflow.log_artifact(str(ARTIFACT_DIR / "feature_names.json"))

        feat_imp = pd.Series(clf.feature_importances_, index=FEATURE_NAMES).sort_values(ascending=False)
        print("Top 10 features by importance:")
        for feat, imp in feat_imp.head(10).items():
            print(f"  {feat}: {imp:.4f}")
            mlflow.log_metric(f"feat_importance_{feat}", float(imp))

        xgb_reg = mlflow.register_model(xgb_uri.model_uri, XGB_MODEL_NAME, await_registration_for=30)
        if_reg  = mlflow.register_model(if_uri.model_uri, IF_MODEL_NAME, await_registration_for=30)

        from mlflow.tracking import MlflowClient
        client = MlflowClient()
        client.set_registered_model_alias(XGB_MODEL_NAME, "champion", version=str(xgb_reg.version))
        client.set_registered_model_alias(IF_MODEL_NAME, "champion", version=str(if_reg.version))

        description = (
            f"XGBoost classifier trained on {len(X_all)} samples, "
            f"{FEATURE_COUNT} features, "
            f"CV accuracy={cv_mean:.3f} +/- {cv_std:.3f}, git_sha={git_sha}"
        )
        client.update_model_version(XGB_MODEL_NAME, version=str(xgb_reg.version), description=description)

        if_description = (
            f"Isolation Forest trained on {len(X_normal)} normal windows, "
            f"precision={if_precision:.3f}, {FEATURE_COUNT} features, "
            f"contamination={IF_CONTAMINATION}, git_sha={git_sha}"
        )
        client.update_model_version(IF_MODEL_NAME, version=str(if_reg.version), description=if_description)

        print(f"Registered XGBoost model: {XGB_MODEL_NAME} v{xgb_reg.version} (champion)")
        print(f"Registered Isolation Forest: {IF_MODEL_NAME} v{if_reg.version} (champion)")

        print(f"Training complete. Artifacts saved to {ARTIFACT_DIR}")


if __name__ == "__main__":
    train()
