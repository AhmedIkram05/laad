"""ML-based anomaly detector — inference + rule-based hybrid.

Loads trained Isolation Forest and XGBoost models from ml/artifacts/.
Queries recent time windows from PostgreSQL, extracts features, and
produces anomaly records for insertion into the anomalies table.

Rule-based detection runs in parallel — always checks for known
anomaly signals in the window regardless of ML output. This ensures
the dashboard always shows anomalies, even when ML confidence is low.

Falls back entirely to rule-based if model artifacts are missing.

Configuration (env vars):
    ML_RULES_DETECTION_ENABLED    : Enable rule-based detection (default: true)
    ML_FALLBACK_ENABLED           : Enable legacy fallback (default: true)

Usage:
    python -m backend.src.anomaly_detection.ml.ml_detector
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import joblib

from backend.src.database.connection import get_cursor
from backend.src.anomaly_detection.ml.feature_engineering import extract_features, FEATURE_NAMES

log = logging.getLogger(__name__)

ARTIFACT_DIR              = Path(__file__).parent / "artifacts"
WINDOW_SECONDS            = 300
CONFIDENCE_THRESHOLD      = 0.60
RULES_DETECTION_ENABLED   = os.getenv("ML_RULES_DETECTION_ENABLED", "true").lower() in ("true", "1", "yes")
FALLBACK_ENABLED          = os.getenv("ML_FALLBACK_ENABLED", "true").lower() in ("true", "1", "yes")

SEVERITY_MAP = {
    "A1": "CRITICAL", "A2": "CRITICAL", "A3": "MAJOR",
    "A4": "MAJOR",    "A5": "MAJOR",    "A6": "MAJOR", "A7": "HIGH",
}
TITLE_MAP = {
    "A1": "ATM offline due to network failure.",
    "A2": "ATM out of service — cash cassettes exhausted.",
    "A3": "JVM memory leak suspected — heap usage increasing.",
    "A4": "Container restart loop causing instability.",
    "A5": "High response time spike and success rate drop.",
    "A6": "OS memory pressure causing application timeouts.",
    "A7": "Malformed or out-of-order Kafka events detected.",
}


class MLAnomalyDetector:
    def __init__(self):
        self._iso:    object | None = None
        self._clf:    object | None = None
        self._le:     object | None = None
        self._loaded = self._load_models()
        
        # Log configuration on init
        log.info(
            "MLAnomalyDetector initialized: rules_enabled=%s, fallback_enabled=%s, models_loaded=%s",
            RULES_DETECTION_ENABLED, FALLBACK_ENABLED, self._loaded
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

    def _query_window(self) -> list[dict]:
        """Query the last WINDOW_SECONDS of data from v_unified_analysis."""
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=WINDOW_SECONDS)
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
            return [dict(r) for r in cur.fetchall()]

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

    def _save_anomaly(self, anomaly_type: str, atm_id: str | None,
                      confidence: float, source: str = "ML") -> None:
        """Insert a detected anomaly into the anomalies table."""
        if self._is_active(anomaly_type, atm_id):
            return

        with get_cursor(commit=True) as cur:
            cur.execute(
                """
                INSERT INTO anomalies
                    (detected_at, anomaly_type, atm_id, model_confidence_score,
                     severity, title, explanation, is_active, is_starred)
                VALUES (%s, %s, %s, %s, %s, %s, %s, 1, 0)
                """,
                (
                    datetime.now(timezone.utc),
                    anomaly_type,
                    atm_id,
                    confidence,
                    SEVERITY_MAP.get(anomaly_type, "HIGH"),
                    TITLE_MAP.get(anomaly_type, f"Anomaly {anomaly_type} detected."),
                    json.dumps({"confidence": confidence, "source": source, "window_seconds": WINDOW_SECONDS}),
                )
            )
        log.info("Saved anomaly %s (atm=%s, confidence=%.2f, source=%s)",
                 anomaly_type, atm_id, confidence, source)

    def _fallback_to_rules(self) -> None:
        """Run the standalone rule-based detector as a fallback path."""
        from backend.src.anomaly_detection.anomaly_detector import AnomalyDetector

        rd = AnomalyDetector()
        data = rd.load_data()
        anomalies = rd.detect_anomalies(data)
        rd.save_anomalies(anomalies)

    def _detect_rules(self, rows: list[dict]) -> list[tuple[str, str | None, float]]:
        """Rule-based detection from payload _anomaly_tag signals in the window.

        Returns list of (anomaly_type, atm_id, confidence) tuples.
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

        detected: list[tuple[str, str | None, float]] = []
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
            detected.append((atype, atm_id, confidence))

        return detected

    def detect_and_save(self) -> int:
        """Run full detection cycle. Returns number of anomalies saved."""
        rows = self._query_window()
        if len(rows) < 5:
            log.debug("Not enough data in window (%d rows) — skipping.", len(rows))
            return 0

        saved = 0

        # Rule-based detection — runs if enabled
        if RULES_DETECTION_ENABLED:
            rule_anomalies = self._detect_rules(rows)
            for atype, atm_id, confidence in rule_anomalies:
                if not self._is_active(atype, atm_id):
                    self._save_anomaly(atype, atm_id, confidence, source="RULES")
                    saved += 1
        else:
            log.debug("Rule-based detection disabled via ML_RULES_DETECTION_ENABLED=false")

        # ML detection — only if models are loaded
        if self._loaded:
            features = extract_features(rows).reshape(1, -1)

            # Stage 1: Isolation Forest
            is_anomaly = self._iso.predict(features)[0] == -1
            if is_anomaly:
                proba     = self._clf.predict_proba(features)[0]
                pred_idx  = int(np.argmax(proba))
                confidence = float(proba[pred_idx])
                label = self._le.inverse_transform([pred_idx])[0]

                log.info("ML: IF anomaly, XGB prediction: %s (confidence=%.2f)",
                         label, confidence)

                if label != "NORMAL" and confidence >= CONFIDENCE_THRESHOLD:
                    atm_ids = [r.get("atm_id") for r in rows if r.get("atm_id")]
                    if atm_ids:
                        atm_id = max(set(atm_ids), key=atm_ids.count)
                    else:
                        atm_id = None
                    if not self._is_active(label, atm_id):
                        self._save_anomaly(label, atm_id, confidence, source="ML")
                        saved += 1
                elif label == "NORMAL" or confidence < CONFIDENCE_THRESHOLD:
                    log.info("ML: confidence %.2f < threshold or NORMAL — rules are primary", confidence)
        elif FALLBACK_ENABLED:
            log.info("ML models not loaded — running legacy fallback detection")
            try:
                self._fallback_to_rules()
            except Exception as exc:
                log.error("Rule-based fallback failed: %s", exc)

        return saved


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    detector = MLAnomalyDetector()
    n = detector.detect_and_save()
    print(f"Saved {n} anomaly/anomalies.")