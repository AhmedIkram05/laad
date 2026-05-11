"""Rule-based anomaly detector using data dictionary field definitions.

Checks the recent window for known anomaly patterns using exact field
names, enum values, and thresholds from the Data Dictionary docs.
Complements ML detection — runs every cycle to ensure dashboard always
shows anomalies regardless of ML accuracy.

Anomaly types mapped to data dictionary fields:
  A1: Network Timeout Cascade   → ATM App + Kafka + Terminal Handler cross-source
  A2: Cash Cassette Low→Empty  → Hardware + Kafka cross-source
  A3: JVM Memory Leak          → Prometheus jvm_memory_used_bytes monotonic rise
  A4: Container Restart Loop   → GCP restart_count + Terminal Handler STARTUP
  A5: High Response Time Spike → Kafka response_time_ms + success_rate drop
  A6: OS Memory Pressure        → Windows OS memory_usage_percent + ATM App TIMEOUT
  A7: Out-of-Order Kafka       → Kafka offset anomalies + null fields
"""
from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from backend.src.database.connection import get_cursor
from backend.src.anomaly_detection.ml.feature_engineering import FEATURE_NAMES

log = logging.getLogger(__name__)

WINDOW_SECONDS = 300

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


def _parse_payload(p: Any) -> dict:
    """Handle both dict (psycopg2 RealDictCursor) and str (legacy/test) payloads."""
    if isinstance(p, dict):
        return p
    if isinstance(p, str):
        try:
            return json.loads(p)
        except (ValueError, TypeError):
            return {}
    return {}


def _query_window() -> list[dict]:
    """Query the last WINDOW_SECONDS from v_unified_analysis."""
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=WINDOW_SECONDS)
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT timestamp, source, atm_id, correlation_id, metric_name, metric_value,
                   event_type, severity, raw_payload, response_time_ms
            FROM v_unified_analysis
            WHERE timestamp >= %s
            ORDER BY timestamp ASC
            """,
            (cutoff,)
        )
        return [dict(r) for r in cur.fetchall()]


def _is_active(anomaly_type: str, atm_id: str | None) -> bool:
    """Skip if same type+atm_id already has an active anomaly."""
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


def _save_anomaly(anomaly_type: str, atm_id: str | None, confidence: float) -> bool:
    """Insert an anomaly. Returns True if saved, False if skipped (duplicate or inactive)."""
    if _is_active(anomaly_type, atm_id):
        return False
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
                json.dumps({"source": "RULES", "window_seconds": WINDOW_SECONDS}),
            )
        )
    log.info("RULES: Saved anomaly %s (atm=%s, confidence=%.2f)", anomaly_type, atm_id, confidence)
    return True


def _detect_a1_network_cascade(rows: list[dict]) -> list[tuple[str, str | None, float]]:
    """A1: Network Timeout Cascade — ATM App NETWORK_DISCONNECT + Kafka Offline + Terminal Handler error."""
    detected: list[tuple[str, str | None, float]] = []
    by_atm: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        if r.get("atm_id"):
            by_atm[r.get("atm_id", "")].append(r)

    for atm_id, atm_rows in by_atm.items():
        has_disconnect = any(
            (r.get("event_type") == "NETWORK_DISCONNECT" or
             _parse_payload(r.get("raw_payload", {})).get("event_type") == "NETWORK_DISCONNECT")
            for r in atm_rows
        )
        has_offline = any(
            ((r.get("atm_status") or "").lower() in ("offline",) or
            (_parse_payload(r.get("raw_payload", {})).get("atm_status") or "").lower() in ("offline",)
            for r in atm_rows
        )
        has_timeout = any(
            (r.get("event_type") in ("TIMEOUT", "NETWORK_TIMEOUT") or
             _parse_payload(r.get("raw_payload", {})).get("event_type") in ("TIMEOUT", "NETWORK_TIMEOUT"))
            for r in atm_rows
        )
        has_th_error = any(
            (r.get("source") == "TERMINAL_HANDLER" and r.get("severity") in ("ERROR", "FATAL")) or
            (r.get("source") == "TERMINAL_HANDLER" and
             _parse_payload(r.get("raw_payload", {})).get("event_type") in ("NETWORK_TIMEOUT", "EXCEPTION"))
            for r in atm_rows
        )

        if has_disconnect and has_offline and (has_timeout or has_th_error):
            detected.append(("A1", atm_id, 0.95))
    return detected


def _detect_a2_cassette_cascade(rows: list[dict]) -> list[tuple[str, str | None, float]]:
    """A2: Cash Cassette Low → Empty cascade — Hardware + Kafka Out of Service."""
    detected: list[tuple[str, str | None, float]] = []
    by_atm: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        if r.get("atm_id"):
            by_atm[r.get("atm_id", "")].append(r)

    for atm_id, atm_rows in by_atm.items():
        event_types = [
            (_parse_payload(r.get("raw_payload", {})).get("event_type") or r.get("event_type"))
            for r in atm_rows
        ]
        has_low    = "CASSETTE_LOW"    in event_types
        has_empty  = "CASSETTE_EMPTY"  in event_types
        has_oos    = any(
            ((r.get("atm_status") or "").lower() in ("out of service", "outservice")
            or (_parse_payload(r.get("raw_payload", {})).get("atm_status") or "").lower() in ("out of service", "outservice")
            for r in atm_rows
        )
        if has_empty and has_oos:
            detected.append(("A2", atm_id, 0.95))
        elif has_low and has_oos:
            detected.append(("A2", atm_id, 0.85))
    return detected


def _detect_a3_jvm_leak(rows: list[dict]) -> list[tuple[str, str | None, float]]:
    """A3: JVM Memory Leak — jvm_memory_used_bytes monotonically rising over window."""
    detected: list[tuple[str, str | None, float]] = []
    by_entity: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        if r.get("metric_name") in ("jvm_memory_used_bytes", "jvm_memory_max_bytes"):
            by_entity[r.get("atm_id") or r.get("entity_id") or ""].append(r)

    for entity_id, entity_rows in by_entity.items():
        jvm_rows = sorted(
            [r for r in entity_rows if r.get("metric_name") == "jvm_memory_used_bytes"],
            key=lambda x: x.get("timestamp") or datetime.min.replace(tzinfo=timezone.utc)
        )
        if len(jvm_rows) < 5:
            continue

        vals = []
        for r in jvm_rows:
            try:
                vals.append(float(r.get("metric_value") or 0))
            except (TypeError, ValueError):
                continue

        if len(vals) < 5:
            continue

        increases = sum(1 for i in range(len(vals) - 1) if vals[i + 1] > vals[i])
        frac = increases / max(1, len(vals) - 1)
        if frac >= 0.5 and vals[-1] > vals[0] * 1.3:
            detected.append(("A3", entity_id if entity_id else None, 0.88))
    return detected


def _detect_a4_container_restart(rows: list[dict]) -> list[tuple[str, str | None, float]]:
    """A4: Container Restart Loop — GCP restart_count > 0 + Terminal Handler STARTUP cascade."""
    detected: list[tuple[str, str | None, float]] = []
    by_atm: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        if r.get("atm_id"):
            by_atm[r.get("atm_id", "")].append(r)

    for atm_id, atm_rows in by_atm.items():
        payloads = [_parse_payload(r.get("raw_payload", {})) for r in atm_rows]

        restart_count = max(
            (float(p.get("restart_count") or 0) for p in payloads),
            default=0.0
        )
        if restart_count > 0:
            th_startups = sum(
                1 for r in atm_rows
                if r.get("source") == "TERMINAL_HANDLER"
                and (r.get("event_type") == "STARTUP" or
                     _parse_payload(r.get("raw_payload", {})).get("event_type") == "STARTUP")
            )
            if th_startups >= 2:
                detected.append(("A4", atm_id, 0.90))
            elif th_startups >= 1:
                detected.append(("A4", atm_id, 0.82))
    return detected


def _detect_a5_response_spike(rows: list[dict]) -> list[tuple[str, str | None, float]]:
    """A5: High Response Time Spike + Success Rate Drop — Kafka/ATM App response_time_ms + transaction_success_rate."""
    detected: list[tuple[str, str | None, float]] = []
    by_atm: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        if r.get("atm_id"):
            by_atm[r.get("atm_id", "")].append(r)

    for atm_id, atm_rows in by_atm.items():
        payloads = [_parse_payload(r.get("raw_payload", {})) for r in atm_rows]

        rt_values = []
        for p in payloads:
            rt = p.get("response_time_ms") or r.get("response_time_ms")
            if rt is not None:
                try:
                    rt_values.append(float(rt))
                except (TypeError, ValueError):
                    pass

        sr_values = []
        for p in payloads:
            sr = (p.get("transaction_success_rate") or p.get("success_rate"))
            if sr is not None:
                try:
                    sr_values.append(float(sr))
                except (TypeError, ValueError):
                    pass

        max_rt = max(rt_values, default=0)
        min_sr = min(sr_values, default=100.0)

        if max_rt > 3000 and min_sr < 90:
            detected.append(("A5", atm_id, 0.90))
        elif max_rt > 2000 and min_sr < 95:
            detected.append(("A5", atm_id, 0.82))
    return detected


def _detect_a6_os_memory_pressure(rows: list[dict]) -> list[tuple[str, str | None, float]]:
    """A6: OS Memory Pressure — Windows OS memory_usage_percent > 90 + ATM App TIMEOUT."""
    detected: list[tuple[str, str | None, float]] = []
    by_atm: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        if r.get("atm_id"):
            by_atm[r.get("atm_id", "")].append(r)

    for atm_id, atm_rows in by_atm.items():
        payloads = [_parse_payload(r.get("raw_payload", {})) for r in atm_rows]

        max_mem = max(
            (float(p.get("memory_usage_percent") or p.get("windows_os_snapshot") or 0))
            for p in payloads
        )
        has_timeout = any(
            (r.get("event_type") == "TIMEOUT" or
             _parse_payload(r.get("raw_payload", {})).get("event_type") == "TIMEOUT")
            for r in atm_rows
        )
        if max_mem >= 90:
            detected.append(("A6", atm_id, 0.88))
        elif max_mem >= 75 and has_timeout:
            detected.append(("A6", atm_id, 0.80))
    return detected


def _detect_a7_out_of_order(rows: list[dict]) -> list[tuple[str, str | None, float]]:
    """A7: Out-of-Order / Malformed Kafka events — offset=-1, missing required fields, null atm_status."""
    detected: list[tuple[str, str | None, float]] = []
    kafka_rows = [r for r in rows if r.get("source") in ("KAFKA", "KAFKA_METRICS")]

    for r in kafka_rows:
        p = _parse_payload(r.get("raw_payload", {}))
        if p.get("offset") == -1 or p.get("_anomaly_tag") == "A7_OUT_OF_ORDER":
            detected.append(("A7", r.get("atm_id") or None, 0.95))
            break

    null_status_kafka = [
        r for r in kafka_rows
        if not (_parse_payload(r.get("raw_payload", {})).get("atm_status")
        and not r.get("atm_status")
        and r.get("source") == "KAFKA"
    ]
    if len(null_status_kafka) >= 3:
        atm_ids = [r.get("atm_id") for r in null_status_kafka if r.get("atm_id")]
        top_atm = max(set(atm_ids), key=atm_ids.count) if atm_ids else None
        detected.append(("A7", top_atm, 0.82))
    return detected


def detect_rules(rows: list[dict] | None = None) -> int:
    """Run full rule-based detection. Returns number of anomalies saved.

    Args:
        rows: Optional pre-fetched window. If None, queries from DB.

    Detection order:
        A1 (network cascade) → A2 (cassette cascade) → A3 (jvm leak)
        → A4 (container restart) → A5 (response spike)
        → A6 (os memory) → A7 (out-of-order)
    """
    if rows is None:
        rows = _query_window()

    if len(rows) < 5:
        log.debug("Not enough data in window (%d rows) — skipping rules.", len(rows))
        return 0

    saved = 0

    for atype, atm_id, confidence in _detect_a1_network_cascade(rows):
        if _save_anomaly(atype, atm_id, confidence):
            saved += 1

    for atype, atm_id, confidence in _detect_a2_cassette_cascade(rows):
        if _save_anomaly(atype, atm_id, confidence):
            saved += 1

    for atype, atm_id, confidence in _detect_a3_jvm_leak(rows):
        if _save_anomaly(atype, atm_id, confidence):
            saved += 1

    for atype, atm_id, confidence in _detect_a4_container_restart(rows):
        if _save_anomaly(atype, atm_id, confidence):
            saved += 1

    for atype, atm_id, confidence in _detect_a5_response_spike(rows):
        if _save_anomaly(atype, atm_id, confidence):
            saved += 1

    for atype, atm_id, confidence in _detect_a6_os_memory_pressure(rows):
        if _save_anomaly(atype, atm_id, confidence):
            saved += 1

    for atype, atm_id, confidence in _detect_a7_out_of_order(rows):
        if _save_anomaly(atype, atm_id, confidence):
            saved += 1

    if saved:
        log.info("RULES: Detected %d anomaly/aggregies in this cycle", saved)
    return saved


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    n = detect_rules()
    print(f"RULES: Saved {n} anomaly/anomalies.")