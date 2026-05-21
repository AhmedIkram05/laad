"""ML-based anomaly detector — inference + hybrid detection.

Loads trained Isolation Forest and XGBoost models from ml/artifacts/.
Queries recent time windows from PostgreSQL, extracts features, and
produces anomaly records for insertion into the anomalies table.

Detection layers (in priority order):
  1. CLASSIFIER: XGBoost + Isolation Forest ensemble (primary). Only active
     when model artifacts exist. Detects known A1–A7 patterns and UNKNOWN
     anomalies via Isolation Forest anomaly score threshold. This is the
     PRIMARY detector — runs first and catches most anomalies.
  2. ZSCORE: Rolling Z-score statistical deviation. Detects novel patterns
     by flagging when current window deviates >3σ from the rolling median.
     INDEPENDENT layer — runs even when CLASSIFIER models fail to load.
  3. SIGNAL_CORRELATOR: Multi-source signal correlation via detect_anomalies_from_window().
     Final fallback layer — deterministic detection of A1–A7 patterns.
     Always runs as safety net.

CLASSIFIER requires loaded models. ZSCORE and SIGNAL_CORRELATOR always run.
All inference cycles are logged to MLflow for observability.

Configuration (env vars):
    ML_SIGNAL_CORRELATOR_ENABLED   : Enable signal correlator detection (default: true)
    MLFLOW_TRACKING_URI      : MLflow server URI (default: http://mlflow:5000)

Usage:
    python -m backend.src.anomaly_detection.ml.ml_detector
"""
from __future__ import annotations

import json
import logging
import os
import re
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path

import joblib
import mlflow
import numpy as np

from backend.src.database.connection import get_cursor
from backend.src.anomaly_detection.ml.feature_engineering import extract_features, FEATURE_NAMES, FEATURE_COUNT
from backend.src.anomaly_detection.anomaly_detector import detect_anomalies_from_window
from backend.src.analytics.analytics_router import increment_anomaly_counter

log = logging.getLogger(__name__)

ARTIFACT_DIR              = Path(__file__).parent / "artifacts"
WINDOW_SECONDS            = int(os.getenv("ML_WINDOW_SECONDS", "60"))
CONFIDENCE_THRESHOLD      = 0.70
UNKNOWN_ANOMALY_THRESHOLD = float(os.getenv("ML_UNKNOWN_THRESHOLD", "-0.75"))
SIGNAL_CORRELATOR_ENABLED = os.getenv("ML_SIGNAL_CORRELATOR_ENABLED", "true").lower() in ("true", "1", "yes")
MLFLOW_TRACKING_URI       = os.getenv("MLFLOW_TRACKING_URI", "http://mlflow:5000")
MLFLOW_EXPERIMENT         = "atm-anomaly-detection"
ZSCORE_WINDOW_SIZE        = 20
ZSCORE_THRESHOLD          = 3.0

SEVERITY_MAP = {
    "A1": "CRITICAL", "A2": "CRITICAL", "A3": "MAJOR",
    "A4": "MAJOR",    "A5": "MAJOR",    "A6": "MAJOR", "A7": "HIGH",
    "UNKNOWN": "HIGH",
}
TITLE_MAP = {
    "A1": "ATM offline due to network failure.",
    "A2": "ATM out of service — cash cassettes exhausted.",
    "A3": "JVM memory leak suspected — heap usage increasing.",
    "A4": "Container restart loop causing instability.",
    "A5": "High response time spike and success rate drop.",
    "A6": "OS memory pressure causing application timeouts.",
    "A7": "Malformed or out-of-order Kafka events detected.",
    "UNKNOWN": "Unusual system behaviour detected — novel anomaly pattern.",
}
SOURCES_MAP = {
    "A1": ["ATM_APP", "KAFKA", "TERMINAL_HANDLER"],
    "A2": ["HARDWARE", "KAFKA"],
    "A3": ["PROMETHEUS", "TERMINAL_HANDLER"],
    "A4": ["GCP", "TERMINAL_HANDLER"],
    "A5": ["KAFKA", "ATM_APP"],
    "A6": ["OS", "ATM_APP"],
    "A7": ["KAFKA", "PROMETHEUS"],
    "UNKNOWN": [],
}
RECOMMENDED_ACTIONS_MAP = {
    "UNKNOWN": (
        "1. Investigate the unusual signal pattern in system telemetry. "
        "2. Cross-reference with recent deployments, config changes, or traffic spikes. "
        "3. Check all data sources (logs, metrics, Kafka) for anomalies. "
        "4. Escalate to senior SRE if pattern persists. "
        "5. Consider adding this pattern to the heuristic or ML model."
    ),
    "A1": (
        "1. Check network connectivity to ATM. "
        "2. Verify router/switch status. "
        "3. Confirm host availability. "
        "4. Once restored, verify ATM status in Kafka dashboard."
    ),
    "A2": (
        "1. Dispatch cash replenishment crew to ATM. "
        "2. Verify cassette fill levels on site. "
        "3. Mark ATM as back in service after replenishment. "
        "4. Review cash usage patterns to optimise refill schedule."
    ),
    "A3": (
        "1. Capture JVM heap dump before restart. "
        "2. Analyse heap dump for memory leaks. "
        "3. Review recent code changes for memory-holding patterns. "
        "4. Consider increasing max heap or scaling the service. "
        "5. Schedule a controlled restart during low-traffic window."
    ),
    "A4": (
        "1. Identify the root cause from container logs before restart. "
        "2. Check resource limits (CPU/memory) in Kubernetes. "
        "3. Review application startup sequence for failure points. "
        "4. If OOM suspected, increase memory limit. "
        "5. Block further restarts with a pre-stop hook if crash loop is harmful."
    ),
    "A5": (
        "1. Identify slow database queries or external service timeouts. "
        "2. Check ATM backend service health and latency. "
        "3. Verify network path between ATM and host systems. "
        "4. Review recent deployments for performance regressions. "
        "5. Scale horizontally if load-related."
    ),
    "A6": (
        "1. Check for memory leaks on the host OS. "
        "2. Review running processes consuming excessive RAM. "
        "3. Investigate application thread pool exhaustion. "
        "4. Consider adding RAM or moving ATM to a higher-capacity host. "
        "5. Schedule maintenance window for OS-level remediation."
    ),
    "A7": (
        "1. Inspect Kafka producer for timestamp misconfiguration. "
        "2. Verify message ordering in Kafka partition. "
        "3. Check Prometheus scraper for parse errors. "
        "4. Validate CSV/JSON schema at ingestion layer. "
        "5. Repair or discard corrupted historical records."
    ),
}


class RollingBaseline:
    """Rolling baseline for Z-score novelty detection.

    Maintains a deque of the last N feature vectors and computes per-feature
    rolling median (μ) and standard deviation (σ). When a new window arrives,
    computes Z-scores: z_i = (x_i - μ_i) / σ_i.

    Features with |z| > ZSCORE_THRESHOLD are flagged as novel deviations.
    """

    def __init__(self, window_size: int = ZSCORE_WINDOW_SIZE):
        self._history: deque[np.ndarray] = deque(maxlen=window_size)

    def update(self, features: np.ndarray) -> None:
        self._history.append(features)

    @property
    def ready(self) -> bool:
        return len(self._history) >= 5

    def compute_z_scores(self, features: np.ndarray) -> np.ndarray:
        if not self.ready:
            return np.zeros(len(features), dtype=np.float32)
        hist = np.stack(list(self._history))
        median = np.median(hist, axis=0)
        std = np.std(hist, axis=0)
        std = np.where(std < 1e-8, 1.0, std)
        z_scores = (features - median) / std
        return z_scores.astype(np.float32)

    def compute_baseline_features(self, features: np.ndarray) -> np.ndarray:
        z_scores = self.compute_z_scores(features)
        return np.array([
            float(np.max(np.abs(z_scores))),
            float(np.mean(np.abs(z_scores))),
            float(np.sum(np.abs(z_scores) > ZSCORE_THRESHOLD)),
            float(np.max(z_scores)),
            float(np.min(z_scores)),
            float(np.mean(z_scores[z_scores > 0])) if np.any(z_scores > 0) else 0.0,
            float(np.mean(z_scores[z_scores < 0])) if np.any(z_scores < 0) else 0.0,
            int(np.any(np.abs(z_scores) > 5.0)),
            int(np.any(np.abs(z_scores) > 4.0)),
            int(np.any(np.abs(z_scores) > 3.0)),
            float(np.std(z_scores)),
            int(np.sum(np.abs(z_scores) > 2.0)),
            int(np.any(np.abs(z_scores) > 3.0)),
        ], dtype=np.float32)


class MLAnomalyDetector:
    def __init__(self):
        self._iso:                 object | None = None
        self._clf:                 object | None = None
        self._le:                  object | None = None
        self._scaler:              object | None = None
        self._if_feature_indices:  list[int] | None = None
        self._if_unknown_threshold: float = UNKNOWN_ANOMALY_THRESHOLD
        self._loaded  = self._load_models()
        self._mlflow_available = False
        self._baseline = RollingBaseline()

        import subprocess
        try:
            git_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL).decode().strip()[:8]
        except Exception:
            git_sha = "unknown"

        try:
            mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
            mlflow.set_experiment(MLFLOW_EXPERIMENT)
            mlflow.set_tag("service", "ml_detector")
            mlflow.set_tag("git_sha", git_sha)
            self._mlflow_available = True
            log.info(
                "MLAnomalyDetector initialized: signal_correlator=%s, "
                "models_loaded=%s, git_sha=%s, mlflow_uri=%s",
                SIGNAL_CORRELATOR_ENABLED, self._loaded, git_sha, MLFLOW_TRACKING_URI
            )
        except Exception as e:
            log.warning(
                "MLflow unavailable (signal_correlator will still run): %s. "
                "MLflow URI=%s",
                e, MLFLOW_TRACKING_URI
            )

    def _load_models(self) -> bool:
        """Attempt to load model artifacts. Returns True on success."""
        try:
            self._iso  = joblib.load(ARTIFACT_DIR / "isolation_forest.joblib")
            self._clf  = joblib.load(ARTIFACT_DIR / "xgb_classifier.joblib")
            self._le   = joblib.load(ARTIFACT_DIR / "label_encoder.joblib")
            self._scaler = joblib.load(ARTIFACT_DIR / "scaler.joblib")

            indices_path = ARTIFACT_DIR / "if_feature_indices.json"
            if indices_path.exists():
                with open(indices_path) as f:
                    self._if_feature_indices = json.load(f)

            threshold_path = ARTIFACT_DIR / "if_unknown_threshold.json"
            if threshold_path.exists():
                with open(threshold_path) as f:
                    data = json.load(f)
                    self._if_unknown_threshold = float(data.get("threshold", UNKNOWN_ANOMALY_THRESHOLD))

            self._loaded = True
            log.info("ML models loaded from %s (indices=%s, threshold=%.4f)",
                      ARTIFACT_DIR,
                      "yes" if self._if_feature_indices else "no",
                      self._if_unknown_threshold)
            return True
        except FileNotFoundError:
            log.warning("Model artifacts not found at %s", ARTIFACT_DIR)
            return False

    def _attribution_for(self, anomaly_type: str, rows: list[dict]) -> str | None:
        """Entity-aware ATM/service attribution per anomaly type.

        All anomaly types must attribute to a valid ATM ID (FK constraint).
        For pod-level anomalies (A3, A4), we extract the ATM from the pod_name
        or fall back to the mode of ATMs in the window.
        """
        atm_ids = [r.get("atm_id") for r in rows if r.get("atm_id")]
        if not atm_ids:
            return None

        if anomaly_type in {"A3", "A4"}:
            # Try to extract ATM from pod_name (e.g., "terminal-handler-atm-gb-0001" -> "ATM-GB-0001")
            for r in rows:
                p = r.get("raw_payload") or {}
                if isinstance(p, str):
                    try:
                        p = json.loads(p)
                    except Exception:
                        p = {}
                pod = p.get("pod_name") or p.get("entity_id")
                if pod and "atm" in str(pod).lower():
                    match = re.search(r'(ATM-[A-Z]{2}-\d{4})', str(pod), re.IGNORECASE)
                    if match:
                        return match.group(1).upper()

        # Fallback: use the mode of ATMs in the window
        return max(set(atm_ids), key=atm_ids.count)

    def _query_window(
        self, window_seconds: int = WINDOW_SECONDS
    ) -> tuple[list[dict], datetime | None, datetime | None]:
        """Query data from v_unified_analysis.

        Attempts the requested window_seconds first. If fewer than 5 rows
        are returned, falls back to a wider 600-second window to avoid
        skipping detection on low-traffic windows.

        Returns:
            Tuple of (rows, window_start, window_end) where start/end are UTC datetimes.
        """
        now = datetime.now(timezone.utc)
        window_end = now
        window_start = now - timedelta(seconds=window_seconds)
        with get_cursor() as cur:
            cur.execute(
                """
                SELECT timestamp, source, atm_id, metric_name, metric_value,
                       event_type, severity, raw_payload, correlation_id,
                       transaction_id, atm_status, component
                FROM v_unified_analysis
                WHERE timestamp >= %s
                ORDER BY timestamp ASC
                """,
                (window_start,)
            )
            rows = [dict(r) for r in cur.fetchall()]

        if len(rows) < 5 and window_seconds > WINDOW_SECONDS:
            return [], None, None
        if len(rows) < 5:
            fallback_end = now
            fallback_start = now - timedelta(seconds=120)
            with get_cursor() as cur:
                cur.execute(
                    """
                    SELECT timestamp, source, atm_id, metric_name, metric_value,
                           event_type, severity, raw_payload, correlation_id,
                           transaction_id, atm_status, component
                    FROM v_unified_analysis
                    WHERE timestamp >= %s
                    ORDER BY timestamp ASC
                    """,
                    (fallback_start,)
                )
                rows = [dict(r) for r in cur.fetchall()]
                window_start = fallback_start
                window_end = fallback_end

        return rows, window_start, window_end

    def _is_active(self, anomaly_type: str, atm_id: str | None) -> bool:
        """Check if an active anomaly of this (type, atm_id) was saved in the last 10 minutes.

        Debounces repeated saves across consecutive 30-second detection cycles.
        Prevents the same anomaly from being written multiple times while it's
        still actively being detected. 10 minutes covers the full lifecycle of
        a single anomaly incident without accumulating stale entries.
        """
        from datetime import timedelta
        window_start = datetime.now(timezone.utc) - timedelta(minutes=10)
        with get_cursor() as cur:
            if atm_id is None:
                cur.execute(
                    "SELECT 1 FROM anomalies WHERE anomaly_type = %s AND atm_id IS NULL AND is_active = 1 AND detected_at >= %s",
                    (anomaly_type, window_start)
                )
            else:
                cur.execute(
                    "SELECT 1 FROM anomalies WHERE anomaly_type = %s AND atm_id = %s AND is_active = 1 AND detected_at >= %s",
                    (anomaly_type, atm_id, window_start)
                )
            return cur.fetchone() is not None

    def _save_anomaly(
        self,
        anomaly_type: str,
        atm_id: str | None,
        confidence: float,
        source: str = "HEURISTIC",
        explanation: dict | None = None,
        sources_involved: list | None = None,
        recommended_action: str | None = None,
        correlation_id: str | None = None,
    ) -> None:
        """Insert a detected anomaly into the anomalies table.

        Args:
            anomaly_type: A1–A7
            atm_id: ATM identifier (may be None for pod-level/service-level anomalies)
            confidence: Detection confidence score (0.0–1.0)
            source: Detection source — HEURISTIC | RULES | ML
            explanation: Additional context dict stored as JSONB
            sources_involved: List of source names contributing to detection
            recommended_action: Human-readable remediation steps
            correlation_id: Cross-source correlation identifier
        """
        if self._is_active(anomaly_type, atm_id):
            return

        title = TITLE_MAP.get(anomaly_type, f"Anomaly {anomaly_type} detected.")
        severity = SEVERITY_MAP.get(anomaly_type, "HIGH")
        sources = sources_involved or SOURCES_MAP.get(anomaly_type, [])
        action = recommended_action or RECOMMENDED_ACTIONS_MAP.get(anomaly_type)
        exp_json = json.dumps({
            "confidence": confidence,
            "source": source,
            "window_seconds": WINDOW_SECONDS,
            **(explanation or {}),
        })

        with get_cursor(commit=True) as cur:
            cur.execute(
                """
                INSERT INTO anomalies
                    (detected_at, anomaly_type, atm_id, model_confidence_score,
                     severity, title, explanation, recommended_action, sources_involved,
                     correlation_id, is_active, is_starred)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 1, 0)
                """,
                (
                    datetime.now(timezone.utc),
                    anomaly_type,
                    atm_id,
                    confidence,
                    severity,
                    title,
                    exp_json,
                    action,
                    json.dumps(sources),
                    correlation_id,
                )
            )
        log.info(
            "Saved anomaly %s (atm=%s, confidence=%.2f, source=%s)",
            anomaly_type, atm_id, confidence, source
        )
        hour_bucket = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H")
        increment_anomaly_counter(anomaly_type, hour_bucket)

    def _detect_heuristic(
        self,
        rows: list[dict],
        window_start: datetime | None,
        window_end: datetime | None,
    ) -> list[dict]:
        """Multi-signal correlation heuristic detection (A1–A7).

        This is the PRIMARY detection layer. It detects real signal patterns
        WITHOUT relying on _anomaly_tag from the generator.

        Returns:
            List of anomaly dicts from detect_anomalies_from_window().
        """
        if not rows:
            return []

        try:
            return detect_anomalies_from_window(rows, window_start, window_end)
        except Exception as e:
            log.error("Heuristic detection failed: %s", e)
            return []

    def detect_and_save(self) -> int:
        """Run full detection cycle across all layers.

        Detection order (priority):
          1. CLASSIFIER: XGBoost + Isolation Forest — primary detector, only if models loaded
             - Runs per-ATM/pod so it can detect multiple anomalies in one cycle
             - Detects: A1–7 (trained) + UNKNOWN (via IF anomaly score threshold)
          2. ZSCORE: Rolling Z-score — always runs (independent of models)
             - Detects: UNKNOWN via >3σ deviation from rolling median
          3. SIGNAL_CORRELATOR: Multi-signal correlation (A1–A7) — final fallback, always runs
             - Detects: A1–7 via deterministic signal patterns

        Returns:
            Total number of anomalies saved this cycle.
        """
        rows, window_start, window_end = self._query_window()
        if len(rows) < 5:
            log.debug("Not enough data in window (%d rows) — skipping.", len(rows))
            return 0

        saved = 0
        heur_anomalies: list = []
        # Track (anomaly_type, atm_id) pairs the classifier already detected this cycle
        classifier_detections: set[tuple[str, str | None]] = set()

        def _run_ml_logging():
            """Internal: log to MLflow if available. Raises on failure."""
            if not self._mlflow_available:
                return
            mlflow.log_metric("rows_processed", len(rows))
            mlflow.log_param("window_seconds", WINDOW_SECONDS)
            mlflow.log_param("signal_correlator_enabled", SIGNAL_CORRELATOR_ENABLED)
            mlflow.log_param("models_loaded", self._loaded)

        # Group rows by atm_id for per-ATM classification and ZSCORE attribution
        atm_groups: dict[str | None, list[dict]] = {}
        for r in rows:
            key = r.get("atm_id")
            atm_groups.setdefault(key, []).append(r)

        # Also extract global features for Z-score baseline (all data combined)
        global_features = extract_features(rows).reshape(1, -1)
        self._baseline.update(global_features.flatten())

        # Most frequent ATM for ZSCORE UNKNOWN attribution
        atm_ids_with_data = [k for k in atm_groups if k is not None]
        most_frequent_atm = max(set(atm_ids_with_data), key=lambda k: len(atm_groups[k])) if atm_ids_with_data else None

        # ─────────────────────────────────────────────────────────────────────────
        # Layer 1: CLASSIFIER DETECTION (Primary — XGBoost + IF ensemble)
        # Groups rows by atm_id/pod and runs the classifier on each group so
        # it can detect multiple anomalies in a single cycle.
        # ─────────────────────────────────────────────────────────────────────────
        if self._loaded:
            for entity_id, entity_rows in atm_groups.items():
                if len(entity_rows) < 3:
                    continue

                try:
                    features = extract_features(entity_rows).reshape(1, -1)
                    if self._scaler is not None:
                        features_scaled = self._scaler.transform(features)
                    else:
                        features_scaled = features
                    if self._if_feature_indices is not None:
                        features_if = features_scaled[:, self._if_feature_indices]
                    else:
                        features_if = features_scaled
                except Exception:
                    continue

                is_anomaly = self._iso.predict(features_if)[0] == -1

                if not is_anomaly:
                    continue

                if_score = float(self._iso.score_samples(features_if)[0])
                proba = self._clf.predict_proba(features)[0]
                pred_idx = int(np.argmax(proba))
                confidence = float(proba[pred_idx])
                label = self._le.inverse_transform([pred_idx])[0]
                log.info("ML[%s]: IF score=%.3f, XGB=%s (conf=%.2f)", entity_id, if_score, label, confidence)

                if label != "NORMAL" and confidence >= CONFIDENCE_THRESHOLD:
                    if not self._is_active(label, entity_id):
                        self._save_anomaly(
                            anomaly_type=label,
                            atm_id=entity_id,
                            confidence=confidence,
                            source="CLASSIFIER",
                            explanation={"if_score": if_score},
                        )
                        saved += 1
                        classifier_detections.add((label, entity_id))
                        log.info("Classifier detected: %s (atm=%s, conf=%.2f)", label, entity_id, confidence)

                elif label == "NORMAL" and if_score <= self._if_unknown_threshold:
                    unknown_confidence = min(abs(if_score) / abs(self._if_unknown_threshold), 1.0) if self._if_unknown_threshold != 0 else 0.5
                    if not self._is_active("UNKNOWN", entity_id):
                        self._save_anomaly(
                            anomaly_type="UNKNOWN",
                            atm_id=entity_id,
                            confidence=round(unknown_confidence, 3),
                            source="CLASSIFIER",
                            explanation={
                                "if_score": if_score,
                                "xgb_predicted": "NORMAL",
                                "xgb_confidence": confidence,
                            },
                        )
                        saved += 1
                        classifier_detections.add(("UNKNOWN", entity_id))
                        log.warning("Classifier detected: UNKNOWN (atm=%s, if_score=%.3f)", entity_id, if_score)

            log.info("ML: %d entity groups classified, %d anomalies saved", len(atm_groups), saved)

        # ─────────────────────────────────────────────────────────────────────────
        # Layer 2: ZSCORE DETECTION (Novel patterns — always runs)
        # Detects: UNKNOWN via rolling Z-score >3σ deviation from historical median
        # ─────────────────────────────────────────────────────────────────────────
        if self._baseline.ready:
            z_scores = self._baseline.compute_z_scores(global_features.flatten())
            max_z = float(np.max(np.abs(z_scores)))
            n_deviating = int(np.sum(np.abs(z_scores) > ZSCORE_THRESHOLD))
            if max_z > ZSCORE_THRESHOLD:
                base_confidence = min(max_z / 5.0, 1.0)
                attributed_atm = max(set(atm_groups.keys() - {None}), key=lambda k: len(atm_groups[k])) if len(atm_groups) > 1 else None
                if not self._is_active("UNKNOWN", attributed_atm):
                    self._save_anomaly(
                        anomaly_type="UNKNOWN",
                        atm_id=attributed_atm,
                        confidence=round(base_confidence, 3),
                        source="ZSCORE",
                        explanation={
                            "max_z_score": round(max_z, 3),
                            "n_features_deviating": n_deviating,
                            "z_threshold": ZSCORE_THRESHOLD,
                            "zscore_window": len(self._baseline._history),
                        },
                    )
                    saved += 1
                    log.warning(
                        "Z-score detected: UNKNOWN (max_z=%.2f, n_deviating=%d, atm=%s)",
                        max_z, n_deviating, attributed_atm
                    )

        # ─────────────────────────────────────────────────────────────────────────
        # Layer 3: SIGNAL_CORRELATOR DETECTION (Final fallback — deterministic)
        # Detects: A1–7 via multi-signal correlation patterns
        # Skips any (type, atm_id) the classifier already caught this cycle.
        # ─────────────────────────────────────────────────────────────────────────
        if SIGNAL_CORRELATOR_ENABLED:
            heur_anomalies = self._detect_heuristic(rows, window_start, window_end)
            for a in heur_anomalies:
                atype = a.get("anomaly_type")
                a_atm = a.get("atm_id")
                if not atype:
                    continue
                # Skip if classifier already detected this (type, atm_id) this cycle
                if (atype, a_atm) in classifier_detections:
                    continue
                if self._is_active(atype, a_atm):
                    continue
                self._save_anomaly(
                    anomaly_type=atype,
                    atm_id=a_atm,
                    confidence=0.95 if atype in {"A1","A2"} else 0.85,
                    source="SIGNAL_CORRELATOR",
                    explanation=json.loads(a.get("explanation", "{}")) if isinstance(a.get("explanation"), str) else (a.get("explanation") or {}),
                    sources_involved=a.get("sources_involved"),
                    recommended_action=a.get("recommended_action"),
                    correlation_id=a.get("correlation_id"),
                )
                saved += 1
                log.info("Signal correlator detected: %s (atm=%s)", atype, a_atm)

        # Log to MLflow only if available — does NOT block detection
        try:
            _run_ml_logging()
            if self._mlflow_available:
                with mlflow.start_run(
                    run_name=f"inference_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}",
                    nested=True,
                ):
                    mlflow.log_metric("classifier_anomalies", len(classifier_detections))
                    mlflow.log_metric("signal_correlator_anomalies", len(heur_anomalies) if SIGNAL_CORRELATOR_ENABLED else 0)
                    mlflow.log_metric("anomalies_saved", saved)
        except Exception as e:
            log.debug("MLflow logging skipped (not critical): %s", e)

        log.info("Inference cycle complete: %d rows, %d anomalies saved", len(rows), saved)
        return saved


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    detector = MLAnomalyDetector()
    n = detector.detect_and_save()
    print(f"Saved {n} anomaly/anomalies.")
