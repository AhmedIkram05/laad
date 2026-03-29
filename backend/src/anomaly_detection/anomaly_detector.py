from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any


class AnomalyDetector:
    """Simple rule-based detector for anomalies A1–A7.

    The detector reads a unified view (or DB) and applies a set of
    heuristics to identify the scenario-based anomalies described in the
    training guide (A1..A7). Primary entry points are `load_data`,
    `detect_anomalies`, and `save_anomalies`.
    """
    def __init__(self, db_path: str | None = None):
        if db_path is None:
            db_path = str(
                Path(__file__).resolve().parents[2]
                / "custom_synthetic_data_sources"
                / "database"
                / "database.db"
            )
        self.db_path = db_path

    def _get_conn(self) -> sqlite3.Connection:
        """Return an SQLite connection configured for this detector.

        Attempts to use the project's central `get_db` helper so PRAGMAs
        (WAL, busy timeout, foreign keys) are applied. Falls back to a
        plain sqlite3 connection if the helper is not available.
        """
        try:
            # Use central helper if available to get PRAGMAs applied
            from backend.src.database.connection import get_db

            conn = get_db(self.db_path)
        except Exception:
            conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def query(self, sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
        """Execute `sql` with `params` and return rows as list of dicts.

        This is a convenience wrapper that opens and closes a connection
        for each query.
        """
        conn = self._get_conn()
        cur = conn.cursor()
        try:
            cur.execute(sql, params)
            rows = cur.fetchall()
            return [dict(r) for r in rows]
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def load_data(self) -> List[Dict[str, Any]]:
        rows = self.query("SELECT * FROM v_unified_analysis ORDER BY timestamp ASC")
        return rows

    def _payload_get(self, row: Dict[str, Any], key: str) -> Any:
        """Get `key` from the row, preferring explicit column then JSON payload.

        Many unified rows store a serialized `raw_payload` or `payload` column
        containing the original input. This helper returns a value from the
        direct column if present, otherwise attempts to parse and read the
        JSON payload.
        """
        # Prefer direct column, else try to read JSON from raw_payload
        if row.get(key) is not None:
            return row.get(key)
        raw = row.get("raw_payload") or row.get("payload")
        if not raw:
            return None
        try:
            p = json.loads(raw) if isinstance(raw, str) else (raw if isinstance(raw, dict) else {})
            return p.get(key)
        except Exception:
            return None

    def _as_float(self, val: Any) -> float | None:
        """Safely coerce `val` to float, returning None on failure.

        Used extensively when parsing metric or kafka numeric fields that
        may be strings or missing.
        """
        if val is None:
            return None
        try:
            return float(val)
        except Exception:
            return None

    def a1_detection(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        '''
        A1: Network Timeout Cascade (ATM-GB-0003, 10:00)
        Sources: ATM App Log, Kafka Stream, Terminal Handler Log
        Correlation ID: `corr-0030-nnet-disc-0001`
        Detection signals:
        ATM App Log: `event_type=NETWORK_DISCONNECT` → `error_code=ERR-0040`
        ATM App Log: `event_type=TIMEOUT` with `response_time_ms=30000`
        Kafka: `atm_status=Offline`, `transaction_failure_reason=HOST_UNAVAILABLE`
        Terminal Handler: `event_type=NETWORK_TIMEOUT` for ATM-GB-0003
        Expected alert: ATM offline due to network failure. Cross-source confirmation.
        '''        
        anomalies: List[Dict[str, Any]] = []
        atm_check: Dict[str, Dict[str, Any]] = {}

        for r in data:
            atm_id = r.get("atm_id") or self._payload_get(r, "atm_id")
            if not atm_id:
                continue
            state = atm_check.setdefault(atm_id, {
                "network_disconnect": False,
                "error_code_correct": False,
                "timeout": False,
                "kafka_offline": False,
                "kafka_host_unavailable": False,
                "terminal_timeout": False,
                "last_ts": r.get("timestamp"),
            })
            state["last_ts"] = r.get("timestamp") or state["last_ts"]

            src = (r.get("source") or "").upper()
            if src == "ATM_APP":
                if r.get("event_type") == "NETWORK_DISCONNECT":
                    if (r.get("error_code") == "ERR-0040") or (self._payload_get(r, "error_code") == "ERR-0040"):
                        state["network_disconnect"] = True
                        state["error_code_correct"] = True
                if r.get("event_type") == "TIMEOUT":
                    rt = r.get("response_time_ms") or self._payload_get(r, "response_time_ms")
                    if rt is not None:
                        try:
                            if int(rt) >= 30000:
                                state["timeout"] = True
                        except Exception:
                            pass

            if src == "KAFKA":
                atm_status = r.get("atm_status") or self._payload_get(r, "atm_status")
                if atm_status == "Offline":
                    state["kafka_offline"] = True
                tfr = r.get("transaction_failure_reason") or self._payload_get(r, "transaction_failure_reason")
                if tfr == "HOST_UNAVAILABLE":
                    state["kafka_host_unavailable"] = True

            if src == "TERMINAL_HANDLER":
                if r.get("event_type") == "NETWORK_TIMEOUT":
                    state["terminal_timeout"] = True

        for atm_id, s in atm_check.items():
            if all([
                s["network_disconnect"],
                s["error_code_correct"],
                s["timeout"],
                s["kafka_offline"],
                s["kafka_host_unavailable"],
                s["terminal_timeout"],
            ]):
                anomalies.append({
                    "anomaly_type": "A1",
                    "atm_id": atm_id,
                    "detected_at": s.get("last_ts") or datetime.now(timezone.utc).isoformat(),
                    "severity": "CRITICAL",
                    "title": "ATM offline due to network failure.",
                    "explanation": json.dumps(s),
                })

        return anomalies

    def a2_detection(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        '''
        Not 100% sure about the a2 anomaly but it the one i seem to understand more and what i understand from it is:
        flag a2 anomaly when we have 2 lows, 2 empties, and then kafka confirms it:

        Sources: ATM Hardware Sensor Log, Kafka Stream
        - Detection signals:
        - Hardware Log: `CASSETTE_LOW` (severity=WARNING) x 2 cassettes
        - Hardware Log: `CASSETTE_EMPTY` (severity=CRITICAL) x 2 cassettes
        - Kafka: `atm_status=Out of Service`, `transaction_failure_reason=CASH_DISPENSE_ERROR`
        - Kafka: `transaction_rate_tps=0.0`, `transaction_success_rate=0.0`
        '''        
        anomalies = []
        checklist: Dict[str, Dict[str, Any]] = {}

        for r in data:
            atm_id = r.get("atm_id") or self._payload_get(r, "atm_id")
            if not atm_id:
                continue
            st = checklist.setdefault(atm_id, {"low": 0, "empty": 0, "kafka_oos": False, "kafka_dispense_error": False, "kafka_trtps_zero": False, "last_ts": r.get("timestamp")})
            st["last_ts"] = r.get("timestamp") or st["last_ts"]

            if r.get("event_type") == "CASSETTE_LOW":
                st["low"] += 1
            if r.get("event_type") == "CASSETTE_EMPTY":
                st["empty"] += 1

            if (r.get("source") or "").upper() == "KAFKA":
                if (r.get("atm_status") or self._payload_get(r, "atm_status")) == "Out of Service":
                    st["kafka_oos"] = True
                if (r.get("transaction_failure_reason") or self._payload_get(r, "transaction_failure_reason")) == "CASH_DISPENSE_ERROR":
                    st["kafka_dispense_error"] = True
                mv = r.get("transaction_rate_tps") or self._payload_get(r, "transaction_rate_tps") or r.get("metric_value")
                try:
                    if mv is not None and float(mv) == 0.0:
                        st["kafka_trtps_zero"] = True
                except Exception:
                    pass

        for atm_id, st in checklist.items():
            if st["empty"] >= 2 and (st["kafka_oos"] or (st["kafka_dispense_error"] and st["kafka_trtps_zero"])):
                anomalies.append({
                    "anomaly_type": "A2",
                    "atm_id": atm_id,
                    "detected_at": st.get("last_ts") or datetime.now(timezone.utc).isoformat(),
                    "severity": "CRITICAL",
                    "title": "ATM out of service - cash cassettes exhausted.",
                    "explanation": json.dumps(st),
                })

        return anomalies

    def a3_detection(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        A3: JVM Memory Leak → OOM (Terminal Handler, 08:00–09:30)
        Sources: Prometheus Metrics, GCP Cloud Metrics, Terminal Handler App Log
        Detection signals:
        Prometheus: `jvm_memory_used_bytes` rising monotonically: 300MB → 1040MB over 90 mins
        Prometheus: `jvm_gc_pause_seconds_sum` increasing: 0.45s → 24.7s (GC thrashing)
        Prometheus: `process_cpu_usage` rising to 0.94 (94%)
        GCP: `container/cpu/usage_time` rising to 94%
        Terminal Handler Log: `OutOfMemoryError` FATAL event
        Expected alert: JVM heap leak detected. GC overhead climbing. OOM imminent.
        """
        anomalies = []
        # Group memory by pod/service
        mem_by_pod: Dict[str, List[float]] = {}
        last_ts_by_pod: Dict[str, str] = {}
        oom_pods: Dict[str, bool] = {}

        for r in data:
            src = (r.get("source") or "").upper()
            # Terminal handler OOM
            if src == "TERMINAL_HANDLER" and (r.get("event_type") == "OOM_ERROR" or r.get("severity") == "FATAL"):
                pod = self._payload_get(r, "pod_name") or r.get("component") or "unknown"
                oom_pods[pod] = True
                # Record first-seen OOM timestamp as the anchor for the leak window
                last_ts_by_pod.setdefault(pod, r.get("timestamp"))

            # Prometheus jvm memory
            if (r.get("metric_name") or "") == "jvm_memory_used_bytes":
                pod = self._payload_get(r, "pod_name") or r.get("component") or "unknown"
                v = self._as_float(r.get("metric_value") or self._payload_get(r, "metric_value"))
                if v is not None:
                    # store timestamped samples so we can window around the OOM event
                    mem_by_pod.setdefault(pod, []).append((r.get("timestamp"), v))

        for pod, series in mem_by_pod.items():
            # Require evidence of OOMs for the pod first
            if not oom_pods.get(pod, False):
                continue
            if not series:
                continue

            # Window the series to the 90 minutes before the recorded OOM event.
            oom_ts_str = last_ts_by_pod.get(pod)
            window_start = None
            window_end = None
            try:
                if oom_ts_str:
                    oom_dt = datetime.fromisoformat(oom_ts_str)
                    window_end = oom_dt
                    window_start = oom_dt - timedelta(minutes=90)
            except Exception:
                window_start = None
                window_end = None

            # Filter samples into the window (timestamps are ISO strings)
            filtered = []
            for tstr, val in series:
                try:
                    tdt = datetime.fromisoformat(tstr)
                except Exception:
                    continue
                if window_start and window_end:
                    if tdt >= window_start and tdt <= window_end:
                        filtered.append(val)
                else:
                    filtered.append(val)

            if len(filtered) < 3:
                continue

            first = filtered[0]
            last = filtered[-1]
            try:
                rel_increase = (last - first) / (first if first != 0 else 1)
            except Exception:
                rel_increase = 0.0

            increases = sum(1 for i in range(len(filtered) - 1) if filtered[i + 1] > filtered[i])
            frac_increase = increases / max(1, len(filtered) - 1)

            # Heuristic: consider a leak if either the relative increase is large
            # or the majority of consecutive samples trend upwards.
            if rel_increase >= 0.2 or frac_increase >= 0.6:
                anomalies.append({
                    "anomaly_type": "A3",
                    "atm_id": None,
                    "detected_at": last_ts_by_pod.get(pod) or datetime.now(timezone.utc).isoformat(),
                    "severity": "MAJOR",
                    "title": "JVM memory leak suspected - heap usage increasing.",
                    "explanation": json.dumps({"pod": pod, "points": filtered[-5:], "rel_increase": rel_increase, "frac_increase": frac_increase}),
                })

        return anomalies

    def a4_detection(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        A4: Container Restart Loop (Terminal Handler, 09:30–09:34)
        Sources: GCP Cloud Metrics, Terminal Handler App Log
        Detection signals:
        GCP: `container/restart_count` = 1, then 2 within 4 minutes
        Terminal Handler Log: `event_type=STARTUP` repeated 3× (container_id changes each time)
        Terminal Handler Log: Two `FATAL OutOfMemoryError` events
        Expected alert: Container crash loop detected. 2 restarts in under 5 minutes.
        """
        anomalies = []
        # GCP: list of (timestamp, restart_count) pairs
        gcp_restarts: List[Dict[str, Any]] = []
        # Terminal handler: global counts
        total_startups = 0
        total_fatals = 0
        last_ts: str | None = None

        for r in data:
            src = (r.get("source") or "").upper()
            last_ts = r.get("timestamp") or last_ts

            if src in ("CLOUD", "GCP"):
                if (r.get("metric_name") or "") == "container/restart_count":
                    v = self._as_float(r.get("metric_value") or self._payload_get(r, "metric_value"))
                    if v is not None:
                        gcp_restarts.append({"ts": r.get("timestamp"), "count": v})

            if src == "TERMINAL_HANDLER":
                if r.get("event_type") == "STARTUP":
                    total_startups += 1
                if r.get("event_type") == "OOM_ERROR" or r.get("severity") == "FATAL":
                    total_fatals += 1

        # Fire if GCP shows >=2 restarts AND terminal handler confirms crash evidence
        if len(gcp_restarts) >= 2 and (total_startups >= 3 or total_fatals >= 2):
            anomalies.append({
                "anomaly_type": "A4",
                "atm_id": None,
                "detected_at": last_ts or datetime.now(timezone.utc).isoformat(),
                "severity": "MAJOR",
                "title": "Container restart loop causing instability.",
                "explanation": json.dumps({
                    "gcp_restarts": gcp_restarts,
                    "total_startups": total_startups,
                    "total_fatals": total_fatals,
                }),
            })

        return anomalies

    def a5_detection(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        A5: High Response Time Spike + Success Rate Drop (ATM-GB-0001, 09:30)
        Sources: Kafka Stream, ATM App Log
        Correlation IDs: `corr-0010-xxyy-aabb-1234`, `corr-0011-xyzw-ccdd-5678`
        Detection signals:
        Kafka: `response_time_ms` = 3200ms then 30000ms (normal: ~290ms)
        Kafka: `transaction_success_rate` drops from 100% to 72% to 50%
        Kafka: `failure_count` = 8, then 14
        ATM App Log: `event_type=TIMEOUT` with `error_code=ERR-0012`
        Expected alert: ATM-GB-0001 response time 10× above baseline. Success rate critically low.
        """
        anomalies = []
        spikes_by_atm: Dict[str, List[Dict[str, Any]]] = {}
        timeouts_by_atm: Dict[str, List[Dict[str, Any]]] = {}
        last_ts: Dict[str, str] = {}

        for r in data:
            atm = r.get("atm_id") or self._payload_get(r, "atm_id")
            if not atm:
                continue
            last_ts.setdefault(atm, r.get("timestamp"))
            if (r.get("source") or "").upper() == "KAFKA":
                rt = self._as_float(r.get("response_time_ms") or self._payload_get(r, "response_time_ms") or r.get("metric_value"))
                sr = self._as_float(r.get("transaction_success_rate") or self._payload_get(r, "transaction_success_rate"))
                fc = self._as_float(r.get("failure_count") or self._payload_get(r, "failure_count"))
                if rt is not None and rt >= 3000:
                    spikes_by_atm.setdefault(atm, []).append({"ts": r.get("timestamp"), "rt": rt, "sr": sr, "fc": fc})

            if (r.get("source") or "").upper() == "ATM_APP":
                if r.get("event_type") == "TIMEOUT" and (r.get("error_code") == "ERR-0012" or self._payload_get(r, "error_code") == "ERR-0012"):
                    timeouts_by_atm.setdefault(atm, []).append({"ts": r.get("timestamp"), "txn": r.get("transaction_id")})

        for atm, spikes in spikes_by_atm.items():
            if len(spikes) >= 2 and timeouts_by_atm.get(atm):
                anomalies.append({
                    "anomaly_type": "A5",
                    "atm_id": atm,
                    "detected_at": last_ts.get(atm) or datetime.now(timezone.utc).isoformat(),
                    "severity": "MAJOR",
                    "title": "High response time spike and success rate drop.",
                    "explanation": json.dumps({"spikes": spikes[-3:], "timeouts": timeouts_by_atm.get(atm)}),
                })

        return anomalies

    def a6_detection(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        A6: OS Memory Pressure → Application Timeout (ATM-GB-0002, 09:45)
        Sources: Windows OS Metrics, ATM App Log
        Detection signals:
        Windows OS Metrics: `memory_usage_percent` escalating: 46% → 98.75% over 2 hours
        Windows OS Metrics: `network_errors` growing: 0 → 22
        Windows OS Metrics: `cpu_usage_percent` rising to 91.5%
        ATM App Log: `event_type=TIMEOUT`, `error_detail` contains "ThreadAbortException" / memory pressure
        Expected alert: ATM host memory critically high. Application timeout correlated with OS pressure.
        """
        anomalies = []
        mem_by_atm: Dict[str, List[float]] = {}
        timeout_evidence: Dict[str, Dict[str, Any]] = {}
        last_ts: Dict[str, str] = {}

        for r in data:
            atm = r.get("atm_id") or self._payload_get(r, "atm_id")
            if not atm:
                continue
            last_ts.setdefault(atm, r.get("timestamp"))

            if (r.get("source") or "").upper() == "OS":
                mem = self._as_float(r.get("memory_usage_percent") or self._payload_get(r, "memory_usage_percent"))
                if mem is not None:
                    mem_by_atm.setdefault(atm, []).append(mem)

            if (r.get("source") or "").upper() == "ATM_APP":
                if r.get("event_type") == "TIMEOUT" and (r.get("error_detail") or "").find("ThreadAbortException") >= 0 or (r.get("error_code") == "ERR-MEM"):
                    timeout_evidence[atm] = {"ts": r.get("timestamp"), "error_detail": r.get("error_detail"), "error_code": r.get("error_code")}

        for atm, mems in mem_by_atm.items():
            max_mem = max(mems) if mems else 0
            if max_mem >= 90 or (len(mems) >= 3 and mems[-1] - mems[0] > 30):
                if atm in timeout_evidence:
                    anomalies.append({
                        "anomaly_type": "A6",
                        "atm_id": atm,
                        "detected_at": last_ts.get(atm) or datetime.now(timezone.utc).isoformat(),
                        "severity": "MAJOR",
                        "title": "OS memory pressure causing application timeouts.",
                        "explanation": json.dumps({"memory_samples": mems[-5:], "timeout": timeout_evidence.get(atm)}),
                    })

        return anomalies

    def a7_detection(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        '''
        A7: Malformed / Out-of-Order Kafka Events (ATM-GB-0004)
        Sources: Kafka Stream, Prometheus Metrics
        Detection signals:
        Kafka offset 4050 has an earlier timestamp than expected (out-of-order)
        Kafka offset 4051: `atm_status=null`, `transaction_rate_tps=null` (missing required fields)
        Prometheus CSV row at 09:33:00 contains `metric_value=890iembre` (non-numeric — malformed)
        Expected alert: Malformed event ingestion detected. Schema validation failure. Out-of-order sequence.
        '''
        anomalies: List[Dict[str, Any]] = []
        kafka_by_atm: Dict[str, List[Dict[str, Any]]] = {}
        kafka_missing_ts: Dict[str, List[str]] = {}
        prom_malformed = False
        prom_malformed_ts: List[str] = []
        last_ts = None

        # Collect evidence from the unified view
        for r in data:
            src = (r.get("source") or "").upper()
            last_ts = r.get("timestamp") or last_ts
            if src == "KAFKA":
                atm = r.get("atm_id") or self._payload_get(r, "atm_id") or "_none_"
                kafka_offset = self._payload_get(r, "kafka_offset")
                kafka_by_atm.setdefault(atm, []).append({
                    "offset": kafka_offset,
                    "ts": r.get("timestamp"),
                    "atm_status": r.get("atm_status"),
                    "transaction_rate_tps": self._payload_get(r, "transaction_rate_tps"),
                    "row": r,
                })
                trtps_val = self._payload_get(r, "transaction_rate_tps")
                if r.get("atm_status") is None or trtps_val is None:
                    kafka_missing_ts.setdefault(atm, []).append(r.get("timestamp"))

            if src in ("METRIC", "PROMETHEUS"):
                if (r.get("metric_name") or "") and r.get("metric_value") is not None:
                    if self._as_float(r.get("metric_value")) is None:
                        prom_malformed = True
                        prom_malformed_ts.append(r.get("timestamp"))

        # Detect kafka out-of-order per ATM
        kafka_out_of_order_atms: set = set()
        for atm, rows in kafka_by_atm.items():
            seq = [(self._as_float(x.get("offset")), x.get("ts")) for x in rows if x.get("offset") is not None]
            seq_sorted = sorted(seq, key=lambda x: x[0])
            for i in range(1, len(seq_sorted)):
                prev_ts = seq_sorted[i - 1][1]
                cur_ts = seq_sorted[i][1]
                try:
                    if prev_ts and cur_ts:
                        prev_dt = datetime.fromisoformat(prev_ts)
                        cur_dt = datetime.fromisoformat(cur_ts)
                        if cur_dt < prev_dt and (prev_dt - cur_dt).total_seconds() >= 60:
                            kafka_out_of_order_atms.add(atm)
                            break
                except Exception:
                    continue

        # Pull ingestion_errors and correlate Prometheus + Kafka failures (±5 minutes)
        err_rows: List[Dict[str, Any]] = []
        try:
            conn = self._get_conn()
            cur = conn.cursor()
            cur.execute("SELECT id, timestamp, source, error_detail, raw_input FROM ingestion_errors ORDER BY timestamp ASC")
            fetched = cur.fetchall()
            for e in fetched:
                try:
                    ets = e[1] if isinstance(e, (list, tuple)) else e["timestamp"]
                    ets_dt = datetime.fromisoformat(ets)
                except Exception:
                    continue
                src = (e[2] if isinstance(e, (list, tuple)) else e["source"]) or ""
                err_rows.append({
                    "id": (e[0] if isinstance(e, (list, tuple)) else e["id"]),
                    "ts": ets_dt,
                    "source": src.upper(),
                    "raw_input": (e[4] if isinstance(e, (list, tuple)) else e["raw_input"]),
                    "error_detail": (e[3] if isinstance(e, (list, tuple)) else e["error_detail"]),
                })
        except Exception:
            err_rows = []
        finally:
            try:
                conn.close()
            except Exception:
                pass

        # Find ingestion_error pairs (PROMETHEUS + KAFKA) that are within 5 minutes
        prom_errs = [e for e in err_rows if e["source"].startswith("PROMETHEUS") or e["source"] == "METRIC"]
        kafka_errs = [e for e in err_rows if e["source"].startswith("KAFKA")]

        paired_errs: List[Dict[str, Any]] = []
        five_min = timedelta(minutes=5)
        for p in prom_errs:
            for k in kafka_errs:
                if abs((p["ts"] - k["ts"]).total_seconds()) <= five_min.total_seconds():
                    paired_errs.append({"prom": p, "kafka": k})

        # Emit A7s for: (1) unified-view evidence (missing fields or out-of-order) + prom malformed,
        # or (2) ingestion_errors showing both PROMETHEUS & KAFKA within ±5 minutes.

        # 1) Unified-view combination
        for atm in set(list(kafka_by_atm.keys())):
            has_missing = bool(kafka_missing_ts.get(atm))
            has_out_of_order = atm in kafka_out_of_order_atms
            if (has_missing or has_out_of_order) and prom_malformed:
                anomalies.append({
                    "anomaly_type": "A7",
                    "atm_id": atm if atm != "_none_" else None,
                    "detected_at": last_ts or datetime.now(timezone.utc).isoformat(),
                    "severity": "HIGH",
                    "title": "Malformed or out-of-order Kafka events correlated with Prometheus parse errors.",
                    "explanation": json.dumps({
                        "atm": atm,
                        "kafka_missing_count": len(kafka_missing_ts.get(atm, [])),
                        "out_of_order": has_out_of_order,
                        "prom_malformed_count": len(prom_malformed_ts),
                    }),
                })

        # 2) ingestion_errors pairs -> try to attribute to ATM via kafka raw_input JSON
        seen_global_pair = False
        for pair in paired_errs:
            kraw = pair["kafka"]["raw_input"]
            attributed_atm = None
            try:
                parsed = json.loads(kraw) if isinstance(kraw, str) else None
                if isinstance(parsed, dict):
                    attributed_atm = parsed.get("atm_id") or parsed.get("entity_id")
            except Exception:
                attributed_atm = None

            anomalies.append({
                "anomaly_type": "A7",
                "atm_id": attributed_atm,
                "detected_at": (pair["kafka"]["ts"].isoformat() if pair["kafka"]["ts"] else last_ts) or datetime.now(timezone.utc).isoformat(),
                "severity": "HIGH",
                "title": "Ingestion errors: Prometheus + Kafka failures detected in same time window.",
                "explanation": json.dumps({
                    "prom_err_id": pair["prom"]["id"],
                    "kafka_err_id": pair["kafka"]["id"],
                    "prom_ts": pair["prom"]["ts"].isoformat(),
                    "kafka_ts": pair["kafka"]["ts"].isoformat(),
                }),
            })
            seen_global_pair = True

        # If prom_malformed but no kafka evidence in unified view, still emit a global Prometheus A7
        if prom_malformed and not paired_errs and not any(a.get("anomaly_type") == "A7" for a in anomalies):
            anomalies.append({
                "anomaly_type": "A7",
                "atm_id": None,
                "detected_at": last_ts or datetime.now(timezone.utc).isoformat(),
                "severity": "HIGH",
                "title": "Malformed Prometheus metric detected.",
                "explanation": json.dumps({"issue": "prometheus_malformed", "samples": prom_malformed_ts}),
            })

        return anomalies

    def detect_anomalies(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        detectors = [
            self.a1_detection,
            self.a2_detection,
            self.a3_detection,
            self.a4_detection,
            self.a5_detection,
            self.a6_detection,
            self.a7_detection,
        ]
        found: List[Dict[str, Any]] = []
        seen = set()
        for fn in detectors:
            try:
                anns = fn(data)
            except Exception:
                anns = []
            for a in anns:
                key = (a.get("anomaly_type"), a.get("atm_id"))
                if key in seen:
                    continue
                seen.add(key)
                found.append(a)
        return found

    def save_anomalies(self, anomalies: List[Dict[str, Any]]) -> int:
        """Persist detected anomalies to the `anomalies` table.

        The function deduplicates by `(anomaly_type, atm_id)` and inserts
        new rows. Returns the number of rows saved.
        """
        if not anomalies:
            print("No anomalies to save.")
            return 0

        conn = self._get_conn()
        cur = conn.cursor()
        saved = 0
        try:
            for a in anomalies:
                anomaly_type = a.get("anomaly_type")
                atm_id = a.get("atm_id")
                detected_at = a.get("detected_at") or datetime.now(timezone.utc).isoformat()
                severity = a.get("severity") or "HIGH"
                title = a.get("title") or ""
                explanation = a.get("explanation") or json.dumps(a)
                correlation_id = a.get("correlation_id")
                transaction_id = a.get("transaction_id")
                sources = a.get("sources_involved") or []

                # dedupe: skip if an entry exists for same anomaly_type + atm_id
                if atm_id is None:
                    cur.execute("SELECT 1 FROM anomalies WHERE anomaly_type = ? AND atm_id IS NULL", (anomaly_type,))
                else:
                    cur.execute("SELECT 1 FROM anomalies WHERE anomaly_type = ? AND atm_id = ?", (anomaly_type, atm_id))
                if cur.fetchone():
                    continue

                cur.execute(
                    "INSERT INTO anomalies (detected_at, anomaly_type, atm_id, correlation_id, transaction_id, model_confidence_score, severity, title, explanation, recommended_action, sources_involved, feedback_rating, is_active, is_starred) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        detected_at,
                        anomaly_type,
                        atm_id,
                        correlation_id,
                        transaction_id,
                        None,
                        severity,
                        title,
                        explanation,
                        None,
                        json.dumps(sources) if not isinstance(sources, str) else sources,
                        None,
                        1,
                        0,
                    ),
                )
                saved += 1
            conn.commit()
        finally:
            try:
                conn.close()
            except Exception:
                pass

        print(f"Saved {saved} anomalies to database.")
        return saved

    def main(self):
        data = self.load_data()
        anns = self.detect_anomalies(data)
        self.save_anomalies(anns)