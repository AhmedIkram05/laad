"""ML-based anomaly detector — inference + hybrid rule/heuristic detection.

Loads trained Isolation Forest and XGBoost models from ml/artifacts/.
Queries recent time windows from PostgreSQL, extracts features, and
produces anomaly records for insertion into the anomalies table.

Detection layers (in priority order):
  1. HEURISTIC: Multi-signal correlation via detect_anomalies_from_window().
     This is the primary layer — it detects real signal patterns (A1–A7)
     WITHOUT relying on _anomaly_tag injected by the generator.
  2. RULES: Tag-reader fallback. Catches _anomaly_tag from payloads that
     may not trigger the heuristic (e.g., generator-injected anomalies
     before enough signal accumulates). Runs for every inference cycle.
  3. ML: Isolation Forest + XGBoost. Only active when model artifacts exist.
     Provides statistical anomaly flagging and type classification.
  4. BASELINE: Rolling Z-score deviation from historical feature windows.
     Detects novel patterns by flagging when current window deviates >3σ
     from the rolling median of recent windows. Runs when ML is loaded.

Rule-based and heuristic detection always run.  ML and baseline run when models are loaded.
All inference cycles are logged to MLflow for observability.

Configuration (env vars):
    ML_HEURISTICS_ENABLED   : Enable heuristic detection (default: true)
    ML_RULES_DETECTION_ENABLED: Enable tag-reader rules (default: true)
    MLFLOW_TRACKING_URI      : MLflow server URI (default: http://mlflow:5000)

Usage:
    python -m backend.src.anomaly_detection.ml.ml_detector
"""
from __future__ import annotations

import json
import logging
import os
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path

import joblib
import mlflow
import numpy as np

from backend.src.database.connection import get_cursor
from backend.src.anomaly_detection.ml.feature_engineering import extract_features, FEATURE_NAMES, FEATURE_COUNT
from backend.src.anomaly_detection.anomaly_detector import detect_anomalies_from_window

log = logging.getLogger(__name__)

ARTIFACT_DIR              = Path(__file__).parent / "artifacts"
WINDOW_SECONDS            = 300
CONFIDENCE_THRESHOLD      = 0.60
UNKNOWN_ANOMALY_THRESHOLD = float(os.getenv("ML_UNKNOWN_THRESHOLD", "-0.1"))
HEURISTICS_ENABLED        = os.getenv("ML_HEURISTICS_ENABLED", "true").lower() in ("true", "1", "yes")
RULES_DETECTION_ENABLED   = os.getenv("ML_RULES_DETECTION_ENABLED", "true").lower() in ("true", "1", "yes")
MLFLOW_TRACKING_URI       = os.getenv("MLFLOW_TRACKING_URI", "http://mlflow:5000")
MLFLOW_EXPERIMENT         = "atm-anomaly-detection"
BASELINE_WINDOW_SIZE      = 20
BASELINE_Z_THRESHOLD      = 3.0

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

    Features with |z| > BASELINE_Z_THRESHOLD are flagged as novel deviations.
    """

    def __init__(self, window_size: int = BASELINE_WINDOW_SIZE):
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
            float(np.sum(np.abs(z_scores) > BASELINE_Z_THRESHOLD)),
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
        self._iso:    object | None = None
        self._clf:    object | None = None
        self._le:     object | None = None
        self._loaded  = self._load_models()
        self._mlflow_available = False
        self._baseline = RollingBaseline()

        try:
            mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
            mlflow.set_experiment(MLFLOW_EXPERIMENT)
            mlflow.set_tag("service", "ml_detector")
            self._mlflow_available = True
            log.info(
                "MLAnomalyDetector initialized: heuristics=%s, rules=%s, "
                "models_loaded=%s, mlflow_uri=%s",
                HEURISTICS_ENABLED, RULES_DETECTION_ENABLED, self._loaded, MLFLOW_TRACKING_URI
            )
        except Exception as e:
            log.warning(
                "MLflow unavailable (heuristics/rules will still run): %s. "
                "MLflow URI=%s",
                e, MLFLOW_TRACKING_URI
            )

    def _load_models(self) -> bool:
        """Attempt to load model artifacts. Returns True on success."""
        try:
            self._iso  = joblib.load(ARTIFACT_DIR / "isolation_forest.joblib")
            self._clf  = joblib.load(ARTIFACT_DIR / "xgb_classifier.joblib")
            self._le   = joblib.load(ARTIFACT_DIR / "label_encoder.joblib")
            self._loaded = True
            log.info("ML models loaded from %s", ARTIFACT_DIR)
            return True
        except FileNotFoundError:
            log.warning("Model artifacts not found at %s", ARTIFACT_DIR)
            return False

    def _attribution_for(self, anomaly_type: str, rows: list[dict]) -> str | None:
        """Entity-aware ATM/service attribution per anomaly type.

        A1, A2, A5, A6 → attribute to the specific ATM that generated the signal.
        A3, A4          → attribute to the pod/container (from payload), not ATM.
        A7              → attribute to the Kafka partition/broker (from payload).
        UNKNOWN         → use the mode of ATMs in the window as fallback.
        """
        atm_ids = [r.get("atm_id") for r in rows if r.get("atm_id")]
        if not atm_ids:
            return None

        if anomaly_type in {"A3", "A4", "A7"}:
            pod_ids = []
            for r in rows:
                p = r.get("raw_payload") or {}
                if isinstance(p, str):
                    try:
                        p = json.loads(p)
                    except Exception:
                        p = {}
                pod = p.get("pod_name") or p.get("entity_id")
                if pod:
                    pod_ids.append(str(pod))
            if pod_ids:
                return max(set(pod_ids), key=pod_ids.count)
            return max(set(atm_ids), key=atm_ids.count)

        if anomaly_type == "UNKNOWN":
            return max(set(atm_ids), key=atm_ids.count)

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
            fallback_start = now - timedelta(seconds=600)
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
        """Check if an active anomaly of this type already exists."""
        with get_cursor() as cur:
            if atm_id is None:
                cur.execute(
                    "SELECT 1 FROM anomalies WHERE anomaly_type = %s AND atm_id IS NULL AND is_active = 1",
                    (anomaly_type,)
                )
            else:
                cur.execute(
                    "SELECT 1 FROM anomalies WHERE anomaly_type = %s AND atm_id = %s AND is_active = 1",
                    (anomaly_type, atm_id)
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

    def _detect_rules(self, rows: list[dict]) -> list[tuple[str, str | None, float, str | None]]:
        """Tag-reader rule-based detection from payload _anomaly_tag signals.

        This is a fast fallback layer that catches _anomaly_tag markers
        directly from payloads. It supplements the heuristic detector but
        should NOT be the primary detection path.

        Returns:
            List of (anomaly_type, atm_id, confidence, correlation_id) tuples.
        """
        def parse_payload(p):
            if isinstance(p, dict):
                return p
            if isinstance(p, str):
                try:
                    return json.loads(p)
                except (ValueError, TypeError):
                    return {}
            return {}

        detected: list[tuple[str, str | None, float, str | None]] = []
        seen: set[tuple[str, str | None]] = set()

        for r in rows:
            payload = parse_payload(r.get("raw_payload") or {})
            tag = payload.get("_anomaly_tag") or payload.get("_anomaly")
            if not tag or not isinstance(tag, str):
                continue

            atype = tag[:2] if tag.startswith("A") and len(tag) >= 2 else None
            if atype not in {"A1","A2","A3","A4","A5","A6","A7"}:
                continue

            atm_id = r.get("atm_id") or None
            key = (atype, atm_id)
            if key in seen:
                continue
            seen.add(key)

            confidence = 0.95 if atype in {"A1","A2"} else 0.85
            correlation_id = payload.get("correlation_id") or r.get("correlation_id")
            detected.append((atype, atm_id, confidence, correlation_id))

        return detected

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

        Layer order:
          1. Heuristic (multi-signal correlation) — always if enabled
          2. Rules (tag reader) — always if enabled
          3. ML (Isolation Forest + XGBoost) — only if models loaded

        Returns:
            Total number of anomalies saved this cycle.
        """
        rows, window_start, window_end = self._query_window()
        if len(rows) < 5:
            log.debug("Not enough data in window (%d rows) — skipping.", len(rows))
            return 0

        saved = 0
        heur_anomalies: list = []
        rule_anomalies: list = []

        def _run_ml_logging():
            """Internal: log to MLflow if available. Raises on failure."""
            if not self._mlflow_available:
                return
            mlflow.log_metric("rows_processed", len(rows))
            mlflow.log_param("window_seconds", WINDOW_SECONDS)
            mlflow.log_param("heuristics_enabled", HEURISTICS_ENABLED)
            mlflow.log_param("rules_enabled", RULES_DETECTION_ENABLED)
            mlflow.log_param("models_loaded", self._loaded)

        # Layer 1: Heuristic detection (primary — always runs)
        if HEURISTICS_ENABLED:
            heur_anomalies = self._detect_heuristic(rows, window_start, window_end)
            for a in heur_anomalies:
                atype = a.get("anomaly_type")
                if not atype:
                    continue
                if self._is_active(atype, a.get("atm_id")):
                    continue
                self._save_anomaly(
                    anomaly_type=atype,
                    atm_id=a.get("atm_id"),
                    confidence=0.95 if atype in {"A1","A2"} else 0.85,
                    source="HEURISTIC",
                    explanation=json.loads(a.get("explanation", "{}")) if isinstance(a.get("explanation"), str) else (a.get("explanation") or {}),
                    sources_involved=a.get("sources_involved"),
                    recommended_action=a.get("recommended_action"),
                    correlation_id=a.get("correlation_id"),
                )
                saved += 1
                log.info("Heuristic detected: %s (atm=%s)", atype, a.get("atm_id"))

        # Layer 2: Tag-reader rules (supplemental — always runs)
        if RULES_DETECTION_ENABLED:
            rule_anomalies = self._detect_rules(rows)
            for atype, atm_id, confidence, correlation_id in rule_anomalies:
                if self._is_active(atype, atm_id):
                    continue
                self._save_anomaly(
                    anomaly_type=atype,
                    atm_id=atm_id,
                    confidence=confidence,
                    source="RULES",
                    correlation_id=correlation_id,
                )
                saved += 1
                log.info("Rule detected: %s (atm=%s)", atype, atm_id)

        # Extract features for all ML layers (runs every cycle)
        features = extract_features(rows).reshape(1, -1)
        self._baseline.update(features.flatten())
        base_features = features

        # Layer 3: ML detection (only when models loaded)
        if self._loaded:
            # Layer 3a: Rolling Z-score baseline novelty detection
            if self._baseline.ready:
                z_scores = self._baseline.compute_z_scores(features.flatten())
                max_z = float(np.max(np.abs(z_scores)))
                n_deviating = int(np.sum(np.abs(z_scores) > BASELINE_Z_THRESHOLD))
                if max_z > BASELINE_Z_THRESHOLD:
                    base_confidence = min(max_z / 5.0, 1.0)
                    if not self._is_active("UNKNOWN", None):
                        self._save_anomaly(
                            anomaly_type="UNKNOWN",
                            atm_id=None,
                            confidence=round(base_confidence, 3),
                            source="BASELINE",
                            explanation={
                                "max_z_score": round(max_z, 3),
                                "n_features_deviating": n_deviating,
                                "z_threshold": BASELINE_Z_THRESHOLD,
                                "baseline_window": len(self._baseline._history),
                            },
                        )
                        saved += 1
                        log.warning(
                            "Novel baseline anomaly: UNKNOWN (max_z=%.2f, n_deviating=%d)",
                            max_z, n_deviating
                        )

            # Layer 3b: Isolation Forest + XGBoost
            is_anomaly = self._iso.predict(base_features)[0] == -1
            log.info("ML: IF anomaly flag=%s", bool(is_anomaly))

            if is_anomaly:
                if_score = float(self._iso.score_samples(base_features)[0])
                proba     = self._clf.predict_proba(base_features)[0]
                pred_idx  = int(np.argmax(proba))
                confidence = float(proba[pred_idx])
                label = self._le.inverse_transform([pred_idx])[0]
                log.info("ML: IF anomaly (score=%.3f), XGB: %s (confidence=%.2f)",
                         if_score, label, confidence)

                attributed_atm_id = self._attribution_for(label, rows)

                if label != "NORMAL" and confidence >= CONFIDENCE_THRESHOLD:
                    if not self._is_active(label, attributed_atm_id):
                        self._save_anomaly(
                            anomaly_type=label,
                            atm_id=attributed_atm_id,
                            confidence=confidence,
                            source="ML",
                            explanation={"if_score": if_score},
                        )
                        saved += 1

                elif label == "NORMAL" and if_score <= UNKNOWN_ANOMALY_THRESHOLD:
                    unknown_confidence = min(abs(if_score) / abs(UNKNOWN_ANOMALY_THRESHOLD), 1.0) if UNKNOWN_ANOMALY_THRESHOLD != 0 else 0.5
                    if not self._is_active("UNKNOWN", attributed_atm_id):
                        self._save_anomaly(
                            anomaly_type="UNKNOWN",
                            atm_id=attributed_atm_id,
                            confidence=round(unknown_confidence, 3),
                            source="ML",
                            explanation={
                                "if_score": if_score,
                                "xgb_predicted": "NORMAL",
                                "xgb_confidence": confidence,
                            },
                        )
                        saved += 1
                        log.warning("Novel anomaly detected: UNKNOWN (atm=%s, if_score=%.3f)",
                                    attributed_atm_id, if_score)

        # Log to MLflow only if available — does NOT block detection
        try:
            _run_ml_logging()
            if self._mlflow_available:
                with mlflow.start_run(
                    run_name=f"inference_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}",
                    nested=True,
                ):
                    mlflow.log_metric("heuristic_anomalies", len(heur_anomalies) if HEURISTICS_ENABLED else 0)
                    mlflow.log_metric("rule_anomalies", len(rule_anomalies) if RULES_DETECTION_ENABLED else 0)
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
