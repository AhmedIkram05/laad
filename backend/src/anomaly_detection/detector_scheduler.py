from __future__ import annotations

import json
import logging
import signal
import time
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any

from apscheduler.schedulers.background import BackgroundScheduler

from backend.src.database.connection import get_conn, release_conn, get_cursor

logger = logging.getLogger(__name__)

# How many seconds between detection runs
DETECTION_INTERVAL_SECONDS = 60

# Keep detections separate per anomaly type (deduplicate on type+atm_id per run)
_seen_this_run: set = set()


class CrossSourceAnomalyDetector:
    """Cross-source anomaly detector that runs continuously.

    Reads from v_unified_analysis, correlates events across sources using
    correlation_id, and saves detected anomalies to the anomalies table.

    Detection is correlation-group based:
    - All events sharing the same correlation_id are treated as one cascade
    - The anomaly type is read from _anomaly_tag in the payload
    - Duplicates within the same run are deduplicated on (anomaly_type, atm_id)
    """

    def load_corr_groups(self) -> Dict[str, List[Dict[str, Any]]]:
        """Load all events grouped by correlation_id from the unified view."""
        conn = get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT * FROM v_unified_analysis
                    WHERE correlation_id IS NOT NULL
                    ORDER BY timestamp ASC
                """)
                rows = cur.fetchall()
        finally:
            release_conn(conn)

        groups: Dict[str, List[Dict[str, Any]]] = {}
        for row in rows:
            d = dict(row)
            cid = d.get("correlation_id")
            if cid:
                groups.setdefault(cid, []).append(d)
        return groups

    def load_metric_groups(self) -> Dict[str, List[Dict[str, Any]]]:
        """Load metrics grouped by entity_id from v_metrics_flat for pattern detection."""
        conn = get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT * FROM v_metrics_flat
                    ORDER BY timestamp ASC
                """)
                rows = cur.fetchall()
        finally:
            release_conn(conn)

        groups: Dict[str, List[Dict[str, Any]]] = {}
        for row in rows:
            d = dict(row)
            eid = d.get("entity_id") or d.get("atm_id")
            if eid:
                groups.setdefault(eid, []).append(d)
        return groups

    def detect_a1_cross_source(self, corr_groups: Dict[str, List[Dict[str, Any]]]) -> List[Dict]:
        """A1: Network Timeout Cascade — ATM_APP + KAFKA + TERMINAL_HANDLER via correlation_id."""
        anomalies = []
        for cid, events in corr_groups.items():
            sources = {e.get("source") for e in events}
            if not {"ATM_APP", "KAFKA", "TERMINAL_HANDLER"}.issubset(sources):
                continue

            # Must have ATM_APP NETWORK_DISCONNECT + TIMEOUT
            atm_events = [e for e in events if e.get("source") == "ATM_APP"]
            event_types = {e.get("event_type") for e in atm_events}
            if not {"NETWORK_DISCONNECT", "TIMEOUT"}.issubset(event_types):
                continue

            # Must have KAFKA STATUS with atm_status
            kafka_events = [e for e in events if e.get("source") == "KAFKA"]
            has_offline = any(
                (e.get("atm_status") or "").lower() == "offline"
                for e in kafka_events
            )
            if not has_offline:
                continue

            # Must have TERMINAL_HANDLER error event
            th_events = [e for e in events if e.get("source") == "TERMINAL_HANDLER"]
            th_errors = [e for e in th_events if e.get("severity") in ("ERROR", "FATAL")]
            if not th_errors:
                continue

            atm_id = events[0].get("atm_id") or events[0].get("entity_id")
            ts = events[0].get("timestamp") or datetime.now(timezone.utc)
            anomalies.append({
                "anomaly_type": "A1",
                "atm_id": atm_id,
                "correlation_id": cid,
                "detected_at": ts,
                "severity": "CRITICAL",
                "title": "ATM offline due to network failure — cross-source cascade confirmed.",
                "explanation": json.dumps({
                    "correlation_id": cid,
                    "sources_involved": list(sources),
                    "atm_id": atm_id,
                    "event_count": len(events),
                }),
            })
        return anomalies

    def detect_a2_cross_source(self, corr_groups: Dict[str, List[Dict[str, Any]]]) -> List[Dict]:
        """A2: Cash Cassette Low → Empty — HARDWARE + KAFKA via correlation_id."""
        anomalies = []
        for cid, events in corr_groups.items():
            hw_events = [e for e in events if e.get("source") == "HARDWARE"]
            event_types = {e.get("event_type") for e in hw_events}
            if not {"CASSETTE_LOW", "CASSETTE_EMPTY"}.issubset(event_types):
                continue

            kafka_events = [e for e in events if e.get("source") == "KAFKA"]
            has_oos = any(
                (e.get("atm_status") or "").lower() in ("out of service", "outservice", "oos")
                for e in kafka_events
            )
            if not has_oos:
                continue

            atm_id = events[0].get("atm_id") or events[0].get("entity_id")
            ts = events[0].get("timestamp") or datetime.now(timezone.utc)
            anomalies.append({
                "anomaly_type": "A2",
                "atm_id": atm_id,
                "correlation_id": cid,
                "detected_at": ts,
                "severity": "CRITICAL",
                "title": "ATM out of service — cash cassettes exhausted.",
                "explanation": json.dumps({
                    "correlation_id": cid,
                    "sources_involved": list({e.get("source") for e in events}),
                    "atm_id": atm_id,
                    "event_count": len(events),
                }),
            })
        return anomalies

    def detect_a4_cross_source(self, corr_groups: Dict[str, List[Dict[str, Any]]]) -> List[Dict]:
        """A4: Container Restart Loop — TERMINAL_HANDLER STARTUP/CRASH cascade via correlation_id."""
        anomalies = []
        for cid, events in corr_groups.items():
            th_events = [e for e in events if e.get("source") == "TERMINAL_HANDLER"]
            if len(th_events) < 2:
                continue

            event_types = [e.get("event_type") for e in th_events]
            has_startup = "STARTUP" in event_types
            has_crash = "CRASH" in event_types

            if not (has_startup and has_crash):
                continue

            if len(th_events) < 3:
                continue

            atm_id = events[0].get("atm_id") or events[0].get("entity_id")
            ts = events[0].get("timestamp") or datetime.now(timezone.utc)
            anomalies.append({
                "anomaly_type": "A4",
                "atm_id": atm_id,
                "correlation_id": cid,
                "detected_at": ts,
                "severity": "HIGH",
                "title": "Container restart loop causing instability.",
                "explanation": json.dumps({
                    "correlation_id": cid,
                    "event_types": event_types,
                    "atm_id": atm_id,
                    "event_count": len(events),
                }),
            })
        return anomalies

    def detect_a7_cross_source(self, corr_groups: Dict[str, List[Dict[str, Any]]]) -> List[Dict]:
        """A7: Malformed/Out-of-Order — KAFKA events with offset=-1 in payload."""
        anomalies = []
        for cid, events in corr_groups.items():
            kafka_events = [e for e in events if e.get("source") == "KAFKA"]
            if not kafka_events:
                continue

            for e in kafka_events:
                payload = e.get("raw_payload") or {}
                if isinstance(payload, dict) and payload.get("offset") == -1:
                    atm_id = e.get("atm_id") or e.get("entity_id")
                    ts = e.get("timestamp") or datetime.now(timezone.utc)
                    anomalies.append({
                        "anomaly_type": "A7",
                        "atm_id": atm_id,
                        "correlation_id": cid,
                        "detected_at": ts,
                        "severity": "HIGH",
                        "title": "Malformed Kafka event injected — offset validation failure.",
                        "explanation": json.dumps({
                            "correlation_id": cid,
                            "source": "KAFKA",
                            "atm_id": atm_id,
                            "offset": -1,
                            "event_type": e.get("event_type"),
                        }),
                    })
        return anomalies

    def detect_a3_metric_pattern(self, groups: Dict[str, List[Dict[str, Any]]]) -> List[Dict]:
        """A3: JVM Memory Leak — monotonically rising jvm_memory_used_bytes detected from metrics."""
        anomalies = []
        for entity_id, rows in groups.items():
            jvm_rows = [
                r for r in rows
                if (r.get("metric_name") or "").startswith("jvm_memory")
                and r.get("metric_value") is not None
            ]
            if len(jvm_rows) < 5:
                continue

            jvm_rows.sort(key=lambda x: x.get("timestamp") or datetime.min)
            values = []
            for r in jvm_rows:
                try:
                    v = float(r.get("metric_value"))
                    values.append(v)
                except (TypeError, ValueError):
                    continue

            if len(values) < 5:
                continue

            increasing = sum(1 for i in range(len(values) - 1) if values[i + 1] > values[i])
            frac = increasing / max(1, len(values) - 1)

            if frac >= 0.6:
                ts = jvm_rows[-1].get("timestamp") or datetime.now(timezone.utc)
                anomalies.append({
                    "anomaly_type": "A3",
                    "atm_id": entity_id,
                    "detected_at": ts,
                    "severity": "HIGH",
                    "title": "JVM memory leak suspected — heap usage increasing monotonically.",
                    "explanation": json.dumps({
                        "entity_id": entity_id,
                        "samples": values[-10:],
                        "increasing_fraction": round(frac, 3),
                        "metric_name": jvm_rows[0].get("metric_name"),
                    }),
                })
        return anomalies

    def detect_a5_metric_pattern(self, groups: Dict[str, List[Dict[str, Any]]]) -> List[Dict]:
        """A5: High Response Time Spike + Success Rate Drop — response_time_ms spikes detected from metrics."""
        anomalies = []
        for entity_id, rows in groups.items():
            kafka_rows = [r for r in rows if r.get("source") == "KAFKA"]
            if not kafka_rows:
                continue

            high_rt = [r for r in kafka_rows
                       if r.get("metric_value") is not None
                       and self._try_float(r.get("metric_value")) > 3000]
            if len(high_rt) < 2:
                continue

            sr_rows = [r for r in kafka_rows
                       if r.get("raw_payload") and isinstance(r.get("raw_payload"), dict)
                       and r.get("raw_payload").get("success_rate") is not None]
            if not sr_rows:
                continue

            success_rates = []
            for r in sr_rows:
                try:
                    sr = float(r.get("raw_payload", {}).get("success_rate"))
                    success_rates.append(sr)
                except (TypeError, ValueError):
                    continue

            if len(success_rates) >= 2:
                first_sr = success_rates[0]
                last_sr = success_rates[-1]
                if last_sr < first_sr * 0.8:
                    ts = kafka_rows[-1].get("timestamp") or datetime.now(timezone.utc)
                    anomalies.append({
                        "anomaly_type": "A5",
                        "atm_id": entity_id,
                        "detected_at": ts,
                        "severity": "HIGH",
                        "title": "High response time spike and success rate drop.",
                        "explanation": json.dumps({
                            "entity_id": entity_id,
                            "high_rt_count": len(high_rt),
                            "success_rate_range": [round(first_sr, 3), round(last_sr, 3)],
                        }),
                    })
        return anomalies

    def detect_a6_metric_pattern(self, groups: Dict[str, List[Dict[str, Any]]]) -> List[Dict]:
        """A6: OS Memory Pressure — windows_os_snapshot memory_usage_percent rising to high levels."""
        anomalies = []
        for entity_id, rows in groups.items():
            os_rows = [r for r in rows if r.get("source") == "OS" and r.get("metric_name") == "windows_os_snapshot"]
            if len(os_rows) < 5:
                continue

            os_rows.sort(key=lambda x: x.get("timestamp") or datetime.min)
            mem_vals = []
            for r in os_rows:
                try:
                    v = float(r.get("metric_value"))
                    mem_vals.append(v)
                except (TypeError, ValueError):
                    continue

            if len(mem_vals) < 5:
                continue

            max_mem = max(mem_vals)
            increase = mem_vals[-1] - mem_vals[0]

            if max_mem >= 90 or increase >= 30:
                ts = os_rows[-1].get("timestamp") or datetime.now(timezone.utc)
                app_timeout = any(
                    e.get("source") == "ATM_APP" and e.get("event_type") == "TIMEOUT"
                    for e in rows
                )
                anomalies.append({
                    "anomaly_type": "A6",
                    "atm_id": entity_id,
                    "detected_at": ts,
                    "severity": "HIGH",
                    "title": "OS memory pressure causing application timeouts.",
                    "explanation": json.dumps({
                        "entity_id": entity_id,
                        "max_memory_pct": round(max_mem, 1),
                        "memory_increase": round(increase, 1),
                        "samples": mem_vals[-5:],
                        "app_timeout_confirmed": app_timeout,
                    }),
                })
        return anomalies

    def _try_float(self, val: Any) -> float | None:
        try:
            return float(val)
        except (TypeError, ValueError):
            return None

    def detect(self) -> List[Dict[str, Any]]:
        """Run full detection cycle across all anomaly types."""
        corr_groups = self.load_corr_groups()
        metric_groups = self.load_metric_groups()

        results = []
        results.extend(self.detect_a1_cross_source(corr_groups))
        results.extend(self.detect_a2_cross_source(corr_groups))
        results.extend(self.detect_a4_cross_source(corr_groups))
        results.extend(self.detect_a7_cross_source(corr_groups))
        results.extend(self.detect_a3_metric_pattern(metric_groups))
        results.extend(self.detect_a5_metric_pattern(metric_groups))
        results.extend(self.detect_a6_metric_pattern(metric_groups))

        return results

    def save(self, anomalies: List[Dict[str, Any]]) -> int:
        """Save detected anomalies, deduplicating on (anomaly_type, atm_id) per run."""
        global _seen_this_run

        saved = 0
        conn = get_conn()
        try:
            with conn.cursor() as cur:
                for a in anomalies:
                    key = (a.get("anomaly_type"), a.get("atm_id"))
                    if key in _seen_this_run:
                        continue
                    _seen_this_run.add(key)

                    cur.execute(
                        "SELECT 1 FROM anomalies WHERE anomaly_type = %s AND atm_id = %s AND is_active = 1",
                        (a.get("anomaly_type"), a.get("atm_id"))
                    )
                    if cur.fetchone():
                        continue

                    cur.execute(
                        """INSERT INTO anomalies
                        (detected_at, anomaly_type, atm_id, correlation_id, transaction_id,
                         model_confidence_score, severity, title, explanation,
                         recommended_action, sources_involved, feedback_rating, is_active, is_starred)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                        (
                            a.get("detected_at") or datetime.now(timezone.utc),
                            a.get("anomaly_type"),
                            a.get("atm_id"),
                            a.get("correlation_id"),
                            None,
                            None,
                            a.get("severity") or "HIGH",
                            a.get("title") or "",
                            a.get("explanation") or "{}",
                            None,
                            Json([a.get("correlation_id")] if a.get("correlation_id") else []),
                            None,
                            1,
                            0,
                        )
                    )
                    saved += 1
            conn.commit()
        finally:
            release_conn(conn)

        return saved


def run_detection():
    """One detection cycle — called by the scheduler."""
    try:
        detector = CrossSourceAnomalyDetector()
        anomalies = detector.detect()
        if anomalies:
            saved = detector.save(anomalies)
            logger.info("Detected %d anomalies, saved %d to DB", len(anomalies), saved)
        else:
            logger.debug("No anomalies detected in this cycle")
    except Exception as exc:
        logger.error("Detection cycle failed: %s", exc, exc_info=True)


def start_scheduler() -> BackgroundScheduler:
    """Start the detection scheduler running indefinitely."""
    sched = BackgroundScheduler()
    sched.add_job(run_detection, "interval", seconds=DETECTION_INTERVAL_SECONDS, id="detector")
    sched.start()
    logger.info("Cross-source anomaly detector scheduler started (interval: %ds)", DETECTION_INTERVAL_SECONDS)
    return sched


def stop_scheduler(sched: BackgroundScheduler):
    """Stop the detection scheduler."""
    sched.shutdown(wait=False)
    logger.info("Cross-source anomaly detector scheduler stopped")