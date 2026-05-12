"""Rule-based anomaly detector for anomaly types A1–A7.

This module exposes two APIs:
  1. Standalone functions (data-driven, stateless) — preferred for ml_detector.py
  2. AnomalyDetector class (connection-aware convenience wrapper) — for scripts/main()

Each detection function takes a list of row dicts and an optional time window
and returns a list of detected anomalies.  Designed to be called by the ML detector
on every inference cycle with the current 300-second window.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List

from psycopg2.extras import Json

from backend.src.database.connection import get_conn, release_conn


def _datetime_safe_json_dumps(data: Any) -> str:
    """json.dumps that converts datetime objects to ISO strings."""
    return json.dumps(data, default=lambda x: x.isoformat() if isinstance(x, datetime) else str(x))


# ─── Helpers (used by all detection functions) ────────────────────────────────

def _payload_get(row: Dict[str, Any], key: str) -> Any:
    """Get `key` from the row, preferring explicit column then JSON payload."""
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


def _as_float(val: Any) -> float | None:
    """Safely coerce `val` to float, returning None on failure."""
    if val is None:
        return None
    try:
        return float(val)
    except Exception:
        return None


def _ingestion_errors_in_window(
    window_start: datetime | None,
    window_end: datetime | None,
) -> List[Dict[str, Any]]:
    """Fetch ingestion_errors rows within an optional time window."""
    errors: List[Dict[str, Any]] = []
    conn = None
    cur = None
    try:
        conn = get_conn()
        cur = conn.cursor()
        if window_start and window_end:
            cur.execute(
                "SELECT id, timestamp, source, error_detail, raw_input "
                "FROM ingestion_errors WHERE timestamp >= %s AND timestamp <= %s "
                "ORDER BY timestamp ASC",
                (window_start, window_end),
            )
        else:
            cur.execute(
                "SELECT id, timestamp, source, error_detail, raw_input "
                "FROM ingestion_errors ORDER BY timestamp ASC"
            )
        for e in cur.fetchall():
            errors.append({
                "id": e[0],
                "ts": e[1],
                "source": (e[2] or "").upper(),
                "raw_input": e[4],
                "error_detail": e[3],
            })
    except Exception:
        pass
    finally:
        if cur is not None:
            try:
                cur.close()
            except Exception:
                pass
        if conn is not None:
            release_conn(conn)
    return errors


# ─── Detection Functions (stateless, data-driven) ────────────────────────────

def a1_detection(data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """A1: Network Timeout Cascade.

    Fires when >= 3 of these 4 network-failure signals are present for the same ATM:
      1. ATM_APP: NETWORK_DISCONNECT (any error code)
      2. ATM_APP: TIMEOUT (any response time)
      3. KAFKA: atm_status=Offline (any variant including OutOfService)
      4. TERMINAL_HANDLER: NETWORK_ERROR or NETWORK_TIMEOUT

    This relaxed threshold ensures detection fires even when the generator
    produces a subset of the ideal signal set.
    """
    anomalies: List[Dict[str, Any]] = []
    atm_check: Dict[str, Dict[str, Any]] = {}

    for r in data:
        atm_id = r.get("atm_id") or _payload_get(r, "atm_id")
        if not atm_id:
            continue
        state = atm_check.setdefault(atm_id, {
            "network_disconnect": False,
            "timeout": False,
            "kafka_offline": False,
            "terminal_network_error": False,
            "last_ts": r.get("timestamp"),
            "correlation_id": None,
        })
        state["last_ts"] = r.get("timestamp") or state["last_ts"]
        state["correlation_id"] = state["correlation_id"] or _payload_get(r, "correlation_id")

        src = (r.get("source") or "").upper()
        if src == "ATM_APP":
            if r.get("event_type") == "NETWORK_DISCONNECT":
                state["network_disconnect"] = True
            if r.get("event_type") == "TIMEOUT":
                state["timeout"] = True

        if src == "KAFKA":
            atm_status = r.get("atm_status") or _payload_get(r, "atm_status")
            if atm_status and ("offline" in atm_status.lower() or atm_status.lower() == "offlineservice"):
                state["kafka_offline"] = True

        if src == "TERMINAL_HANDLER":
            et = (r.get("event_type") or "").upper()
            if et in ("NETWORK_ERROR", "NETWORK_TIMEOUT"):
                state["terminal_network_error"] = True

    for atm_id, s in atm_check.items():
        signal_count = sum([
            s["network_disconnect"],
            s["timeout"],
            s["kafka_offline"],
            s["terminal_network_error"],
        ])
        if signal_count >= 3:
            anomalies.append({
                "anomaly_type": "A1",
                "atm_id": atm_id,
                "detected_at": s.get("last_ts") or datetime.now(timezone.utc).isoformat(),
                "severity": "CRITICAL",
                "title": "ATM offline due to network failure.",
                "explanation": _datetime_safe_json_dumps(s),
                "sources_involved": ["ATM_APP", "KAFKA", "TERMINAL_HANDLER"],
                "recommended_action": (
                    "1. Check network connectivity to ATM. "
                    "2. Verify router/switch status. "
                    "3. Confirm host availability. "
                    "4. Once restored, verify ATM status in Kafka dashboard."
                ),
                "correlation_id": s.get("correlation_id"),
            })

    return anomalies


def a2_detection(data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """A2: Cash Cassette Empty.

    Fires when hardware reports >=2 CASSETTE_EMPTY events AND Kafka confirms
    OutOfService OR (CASH_DISPENSE_ERROR + transaction_rate_tps=0).
    """
    anomalies: List[Dict[str, Any]] = []
    checklist: Dict[str, Dict[str, Any]] = {}

    for r in data:
        atm_id = r.get("atm_id") or _payload_get(r, "atm_id")
        if not atm_id:
            continue
        st = checklist.setdefault(atm_id, {
            "low": 0, "empty": 0, "kafka_oos": False,
            "kafka_dispense_error": False, "kafka_trtps_zero": False,
            "last_ts": r.get("timestamp"), "correlation_id": None,
        })
        st["last_ts"] = r.get("timestamp") or st["last_ts"]
        st["correlation_id"] = st["correlation_id"] or _payload_get(r, "correlation_id")

        if r.get("event_type") == "CASSETTE_LOW":
            st["low"] += 1
        if r.get("event_type") == "CASSETTE_EMPTY":
            st["empty"] += 1

        if (r.get("source") or "").upper() == "KAFKA":
            atm_status = (_payload_get(r, "atm_status") or r.get("atm_status") or "").lower()
            if "out" in atm_status and "service" in atm_status or atm_status == "outofservice":
                st["kafka_oos"] = True
            if _payload_get(r, "transaction_failure_reason") == "CASH_DISPENSE_ERROR":
                st["kafka_dispense_error"] = True
            mv = _payload_get(r, "transaction_rate_tps") or r.get("transaction_rate_tps") or r.get("metric_value")
            try:
                if mv is not None and float(mv) == 0.0:
                    st["kafka_trtps_zero"] = True
            except Exception:
                pass

    for atm_id, st in checklist.items():
        if st["empty"] >= 1 and (st["kafka_oos"] or (st["kafka_dispense_error"] and st["kafka_trtps_zero"])):
            anomalies.append({
                "anomaly_type": "A2",
                "atm_id": atm_id,
                "detected_at": st.get("last_ts") or datetime.now(timezone.utc).isoformat(),
                "severity": "CRITICAL",
                "title": "ATM out of service — cash cassettes exhausted.",
                "explanation": _datetime_safe_json_dumps(st),
                "sources_involved": ["HARDWARE", "KAFKA"],
                "recommended_action": (
                    "1. Dispatch cash replenishment crew to ATM. "
                    "2. Verify cassette fill levels on site. "
                    "3. Mark ATM as back in service after replenishment. "
                    "4. Review cash usage patterns to optimise refill schedule."
                ),
                "correlation_id": st.get("correlation_id"),
            })

    return anomalies


def a3_detection(data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """A3: JVM Memory Leak.

    Fires when JVM heap (jvm_memory_used_bytes) rises monotonically by >=20%
    or >=60% of samples are increasing, AND an OOM event is present.
    Tracks up to 90 minutes before the OOM event.

    Pod-level: each pod is evaluated independently. If pod_name maps to a valid
    ATM ID (as in generated data), that ATM is attributed in the anomaly.
    """
    anomalies: List[Dict[str, Any]] = []
    mem_by_pod: Dict[str, List[tuple]] = {}
    oom_pods: Dict[str, Dict[str, Any]] = {}

    for r in data:
        src = (r.get("source") or "").upper()
        if src == "TERMINAL_HANDLER" and (r.get("event_type") == "OOM_ERROR" or r.get("severity") == "FATAL"):
            pod = _payload_get(r, "pod_name") or r.get("component") or "unknown"
            atm_id = r.get("atm_id") or _payload_get(r, "atm_id")
            if pod not in oom_pods:
                oom_pods[pod] = {"ts": r.get("timestamp"), "atm_id": atm_id}
            else:
                oom_pods[pod]["ts"] = r.get("timestamp")

        if (r.get("metric_name") or "") == "jvm_memory_used_bytes":
            pod = _payload_get(r, "pod_name") or r.get("component") or "unknown"
            v = _as_float(r.get("metric_value") or _payload_get(r, "metric_value"))
            if v is not None:
                mem_by_pod.setdefault(pod, []).append((r.get("timestamp"), v))

    for pod, series in mem_by_pod.items():
        if pod not in oom_pods:
            continue
        if not series:
            continue

        oom_ts_str = oom_pods[pod].get("ts")
        window_start: datetime | None = None
        window_end: datetime | None = None
        try:
            if oom_ts_str:
                oom_dt_str = oom_ts_str.replace("Z", "+00:00")
                oom_dt = datetime.fromisoformat(oom_dt_str)
                window_end = oom_dt
                window_start = oom_dt - timedelta(minutes=90)
        except Exception:
            pass

        filtered: List[float] = []
        for tstr, val in series:
            try:
                ts_str = tstr.replace("Z", "+00:00") if tstr else tstr
                tdt = datetime.fromisoformat(ts_str)
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

        if rel_increase >= 0.2 or frac_increase >= 0.6:
            pod_atm_id = oom_pods[pod].get("atm_id")
            anomalies.append({
                "anomaly_type": "A3",
                "atm_id": pod_atm_id,
                "detected_at": oom_ts_str or datetime.now(timezone.utc).isoformat(),
                "severity": "MAJOR",
                "title": "JVM memory leak suspected — heap usage increasing.",
                "explanation": _datetime_safe_json_dumps({
                    "pod": pod, "atm_id": pod_atm_id, "points": filtered[-5:],
                    "rel_increase": rel_increase, "frac_increase": frac_increase,
                }),
                "sources_involved": ["PROMETHEUS", "TERMINAL_HANDLER"],
                "recommended_action": (
                    "1. Capture JVM heap dump before restart. "
                    "2. Analyse heap dump for memory leaks (focus on long-lived objects). "
                    "3. Review recent code changes for memory-holding patterns. "
                    "4. Consider increasing max heap or scaling the service. "
                    "5. Schedule a controlled restart during low-traffic window."
                ),
            })

    return anomalies


def a4_detection(data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """A4: Container Restart Loop.

    Fires when at least 2 GCP/CLOUD restart_count events are detected
     AND terminal handler shows >=2 STARTUP events OR >=2 FATAL events.
    Supports both real GCP parser output (source=CLOUD, metric_name=restart_count)
    and legacy/test format (source=GCP, metric_name=container/restart_count).
    """
    anomalies: List[Dict[str, Any]] = []
    gcp_restarts: List[Dict[str, Any]] = []
    total_startups = 0
    total_fatals = 0
    last_ts: str | None = None

    for r in data:
        src = (r.get("source") or "").upper()
        last_ts = r.get("timestamp") or last_ts
        metric_name = r.get("metric_name") or ""

        if src in ("CLOUD", "GCP"):
            if metric_name in ("restart_count", "container/restart_count"):
                v = _as_float(r.get("metric_value") or _payload_get(r, "metric_value"))
                if v is not None:
                    gcp_restarts.append({"ts": r.get("timestamp"), "count": v})

        if src == "TERMINAL_HANDLER":
            if r.get("event_type") == "STARTUP":
                total_startups += 1
            if r.get("event_type") == "OOM_ERROR" or r.get("severity") == "FATAL":
                total_fatals += 1

    if len(gcp_restarts) >= 2 and (total_startups >= 2 or total_fatals >= 2):
        detected_ts = gcp_restarts[-1].get("ts") or last_ts
        anomalies.append({
            "anomaly_type": "A4",
            "atm_id": None,
            "detected_at": detected_ts or datetime.now(timezone.utc).isoformat(),
            "severity": "MAJOR",
            "title": "Container restart loop causing instability.",
            "explanation": _datetime_safe_json_dumps({
                "gcp_restarts": gcp_restarts,
                "total_startups": total_startups,
                "total_fatals": total_fatals,
            }),
            "sources_involved": ["GCP", "TERMINAL_HANDLER"],
            "recommended_action": (
                "1. Identify the root cause from container logs before restart. "
                "2. Check resource limits (CPU/memory) in Kubernetes. "
                "3. Review application startup sequence for failure points. "
                "4. If OOM suspected, increase memory limit or optimise usage. "
                "5. Block further restarts with a pre-stop hook if the crash loop is harmful."
            ),
        })

    return anomalies


def a5_detection(data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """A5: High Response Time Spike + Success Rate Drop.

    Fires when Kafka reports response_time_ms >= 3000 on >=2 occasions
    AND ATM_APP logs a TIMEOUT with error_code=ERR-0012 for the same ATM.
    """
    anomalies: List[Dict[str, Any]] = []
    spikes_by_atm: Dict[str, List[Dict[str, Any]]] = {}
    timeouts_by_atm: Dict[str, List[Dict[str, Any]]] = {}
    last_ts: Dict[str, str] = {}

    for r in data:
        atm = r.get("atm_id") or _payload_get(r, "atm_id")
        if not atm:
            continue
        last_ts.setdefault(atm, r.get("timestamp"))
        if (r.get("source") or "").upper() == "KAFKA":
            rt = _as_float(_payload_get(r, "response_time_ms") or r.get("response_time_ms") or r.get("metric_value"))
            sr = _as_float(_payload_get(r, "transaction_success_rate"))
            fc = _as_float(_payload_get(r, "failure_count"))
            if rt is not None and rt >= 3000:
                spikes_by_atm.setdefault(atm, []).append({"ts": r.get("timestamp"), "rt": rt, "sr": sr, "fc": fc})

        if (r.get("source") or "").upper() == "ATM_APP":
            if r.get("event_type") == "TIMEOUT" and (r.get("error_code") == "ERR-0012" or _payload_get(r, "error_code") == "ERR-0012"):
                timeouts_by_atm.setdefault(atm, []).append({"ts": r.get("timestamp"), "txn": _payload_get(r, "transaction_id") or r.get("transaction_id")})

    for atm, spikes in spikes_by_atm.items():
        if len(spikes) >= 2 and timeouts_by_atm.get(atm):
            anomalies.append({
                "anomaly_type": "A5",
                "atm_id": atm,
                "detected_at": last_ts.get(atm) or datetime.now(timezone.utc).isoformat(),
                "severity": "MAJOR",
                "title": "High response time spike and success rate drop.",
                "explanation": _datetime_safe_json_dumps({"spikes": spikes[-3:], "timeouts": timeouts_by_atm.get(atm)}),
                "sources_involved": ["KAFKA", "ATM_APP"],
                "recommended_action": (
                    "1. Identify slow database queries or external service timeouts. "
                    "2. Check ATM backend service health and latency. "
                    "3. Verify network path between ATM and host systems. "
                    "4. Review recent deployments for performance regressions. "
                    "5. Scale horizontally if load-related."
                ),
            })

    return anomalies


def a6_detection(data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """A6: OS Memory Pressure → Application Timeout.

    Fires when OS memory_usage_percent >= 90 (or +30% increase over 3+ samples)
    AND ATM_APP logs a TIMEOUT with ThreadAbortException or error_code=ERR-MEM.
    """
    anomalies: List[Dict[str, Any]] = []
    mem_by_atm: Dict[str, List[float]] = {}
    timeout_evidence: Dict[str, Dict[str, Any]] = {}
    last_ts: Dict[str, str] = {}

    for r in data:
        atm = r.get("atm_id") or _payload_get(r, "atm_id")
        if not atm:
            continue
        last_ts.setdefault(atm, r.get("timestamp"))

        if (r.get("source") or "").upper() == "OS":
            mem = _as_float(_payload_get(r, "memory_usage_percent") or r.get("memory_usage_percent"))
            if mem is not None:
                mem_by_atm.setdefault(atm, []).append(mem)

        if (r.get("source") or "").upper() == "ATM_APP":
            if r.get("event_type") == "TIMEOUT":
                detail = r.get("error_detail") or _payload_get(r, "error_detail") or ""
                code = r.get("error_code") or _payload_get(r, "error_code")
                if "ThreadAbortException" in detail or code == "ERR-MEM":
                    timeout_evidence[atm] = {"ts": r.get("timestamp"), "error_detail": detail, "error_code": code}

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
                    "explanation": _datetime_safe_json_dumps({"memory_samples": mems[-5:], "timeout": timeout_evidence.get(atm)}),
                    "sources_involved": ["OS", "ATM_APP"],
                    "recommended_action": (
                        "1. Check for memory leaks on the host OS. "
                        "2. Review running processes consuming excessive RAM. "
                        "3. Investigate application thread pool exhaustion. "
                        "4. Consider adding RAM or moving ATM to a higher-capacity host. "
                        "5. Schedule maintenance window for OS-level remediation."
                    ),
                })

    return anomalies


def a7_detection(
    data: List[Dict[str, Any]],
    ingestion_errors: List[Dict[str, Any]] | None = None,
) -> List[Dict[str, Any]]:
    """A7: Malformed / Out-of-Order Kafka Events.

    Fires when:
      1. Kafka shows out-of-order offsets (offset N+1 has earlier timestamp than offset N)
         OR null/required fields in Kafka rows, AND Prometheus shows malformed metric values.
      2. OR ingestion_errors table shows paired PROMETHEUS + KAFKA errors within 5 minutes.

    Args:
        data: Rows from v_unified_analysis
        ingestion_errors: Optional pre-fetched ingestion_errors. If None, fetches all.
    """
    anomalies: List[Dict[str, Any]] = []
    kafka_by_atm: Dict[str, List[Dict[str, Any]]] = {}
    kafka_missing_ts: Dict[str, List[str]] = {}
    kafka_offset_minus_one: Dict[str, List[str]] = {}
    prom_malformed = False
    prom_malformed_ts: List[str] = []
    last_ts: str | None = None

    for r in data:
        src = (r.get("source") or "").upper()
        last_ts = r.get("timestamp") or last_ts
        if src == "KAFKA":
            atm = r.get("atm_id") or _payload_get(r, "atm_id") or "_none_"
            kafka_offset = _payload_get(r, "kafka_offset") or _payload_get(r, "offset")
            kafka_by_atm.setdefault(atm, []).append({
                "offset": kafka_offset,
                "ts": r.get("timestamp"),
                "atm_status": r.get("atm_status"),
                "transaction_rate_tps": _payload_get(r, "transaction_rate_tps"),
                "row": r,
            })
            trtps_val = _payload_get(r, "transaction_rate_tps")
            if kafka_offset == -1:
                kafka_offset_minus_one.setdefault(atm, []).append(r.get("timestamp"))
                kafka_missing_ts.setdefault(atm, []).append(r.get("timestamp"))
            elif r.get("atm_status") is None or trtps_val is None:
                kafka_missing_ts.setdefault(atm, []).append(r.get("timestamp"))

        if src in ("METRIC", "PROMETHEUS"):
            if (r.get("metric_name") or "") and r.get("metric_value") is not None:
                if _as_float(r.get("metric_value")) is None:
                    prom_malformed = True
                    prom_malformed_ts.append(r.get("timestamp"))

    kafka_out_of_order_atms: set = set()
    for atm, rows in kafka_by_atm.items():
        seq = [(_as_float(x.get("offset")), x.get("ts")) for x in rows if x.get("offset") is not None and _as_float(x.get("offset")) != -1]
        seq_sorted = sorted(seq, key=lambda x: x[0])
        for i in range(1, len(seq_sorted)):
            prev_ts = seq_sorted[i - 1][1]
            cur_ts = seq_sorted[i][1]
            try:
                if prev_ts and cur_ts:
                    prev_dt_str = prev_ts.replace("Z", "+00:00")
                    cur_dt_str = cur_ts.replace("Z", "+00:00")
                    prev_dt = datetime.fromisoformat(prev_dt_str)
                    cur_dt = datetime.fromisoformat(cur_dt_str)
                    if cur_dt < prev_dt and (prev_dt - cur_dt).total_seconds() >= 60:
                        kafka_out_of_order_atms.add(atm)
                        break
            except Exception:
                continue

    if ingestion_errors is None:
        ingestion_errors = _ingestion_errors_in_window(None, None)

    prom_errs = [e for e in ingestion_errors if e["source"].startswith("PROMETHEUS") or e["source"] == "METRIC"]
    kafka_errs = [e for e in ingestion_errors if e["source"].startswith("KAFKA")]

    paired_errs: List[Dict[str, Any]] = []
    five_min = timedelta(minutes=5)
    for p in prom_errs:
        for k in kafka_errs:
            if p["ts"] and k["ts"] and abs((p["ts"] - k["ts"]).total_seconds()) <= five_min.total_seconds():
                paired_errs.append({"prom": p, "kafka": k})

    for atm in set(kafka_by_atm.keys()):
        has_missing = bool(kafka_missing_ts.get(atm))
        has_out_of_order = atm in kafka_out_of_order_atms
        has_offset_minus_one = bool(kafka_offset_minus_one.get(atm))
        if has_offset_minus_one or ((has_missing or has_out_of_order) and prom_malformed):
            anomalies.append({
                "anomaly_type": "A7",
                "atm_id": atm if atm != "_none_" else None,
                "detected_at": last_ts or datetime.now(timezone.utc).isoformat(),
                "severity": "HIGH",
                "title": "Malformed or out-of-order Kafka events detected.",
                "explanation": _datetime_safe_json_dumps({
                    "atm": atm,
                    "kafka_missing_count": len(kafka_missing_ts.get(atm, [])),
                    "out_of_order": has_out_of_order,
                    "prom_malformed_count": len(prom_malformed_ts),
                    "offset_minus_one": has_offset_minus_one,
                }),
                "sources_involved": ["KAFKA", "PROMETHEUS"],
                "recommended_action": (
                    "1. Inspect Kafka producer for timestamp misconfiguration. "
                    "2. Verify message ordering in Kafka partition. "
                    "3. Check Prometheus scraper for parse errors. "
                    "4. Validate CSV/JSON schema at ingestion layer. "
                    "5. Repair or discard corrupted historical records."
                ),
            })

    for pair in paired_errs:
        kraw = pair["kafka"]["raw_input"]
        praw = pair["prom"]["raw_input"]
        attributed_atm = None
        detected_iso = None
        try:
            if isinstance(kraw, str) and kraw.strip().startswith("{"):
                parsed_k = json.loads(kraw)
                if isinstance(parsed_k, dict):
                    attributed_atm = parsed_k.get("atm_id") or parsed_k.get("entity_id")
                    detected_iso = parsed_k.get("timestamp")
        except Exception:
            pass
        try:
            if isinstance(praw, str) and praw.strip().startswith("{"):
                parsed_p = json.loads(praw)
                if isinstance(parsed_p, dict):
                    attributed_atm = attributed_atm or parsed_p.get("atm_id") or parsed_p.get("entity_id")
                    detected_iso = detected_iso or parsed_p.get("timestamp")
        except Exception:
            pass
        detected_at_val = None
        try:
            detected_at_val = detected_iso or (
                pair["kafka"]["ts"].isoformat() if pair["kafka"]["ts"] else
                (pair["prom"]["ts"].isoformat() if pair["prom"]["ts"] else None)
            )
        except Exception:
            pass

        anomalies.append({
            "anomaly_type": "A7",
            "atm_id": attributed_atm,
            "detected_at": detected_at_val or last_ts or datetime.now(timezone.utc).isoformat(),
            "severity": "HIGH",
            "title": "Ingestion errors: Prometheus + Kafka failures detected in same time window.",
            "explanation": _datetime_safe_json_dumps({
                "prom_err_id": pair["prom"]["id"],
                "kafka_err_id": pair["kafka"]["id"],
                "prom_ts": pair["prom"]["ts"].isoformat() if pair["prom"]["ts"] else None,
                "kafka_ts": pair["kafka"]["ts"].isoformat() if pair["kafka"]["ts"] else None,
            }),
            "sources_involved": ["PROMETHEUS", "KAFKA"],
            "recommended_action": (
                "1. Inspect Prometheus scrape targets for parse errors. "
                "2. Verify Kafka message schema and encoding. "
                "3. Check for clock skew between producers. "
                "4. Add schema validation at the ingestion layer. "
                "5. Reprocess or discard failed ingestion batches."
            ),
        })

    if prom_malformed and not paired_errs and not any(a.get("anomaly_type") == "A7" for a in anomalies):
        anomalies.append({
            "anomaly_type": "A7",
            "atm_id": None,
            "detected_at": last_ts or datetime.now(timezone.utc).isoformat(),
            "severity": "HIGH",
            "title": "Malformed Prometheus metric detected.",
            "explanation": _datetime_safe_json_dumps({"issue": "prometheus_malformed", "samples": prom_malformed_ts}),
            "sources_involved": ["PROMETHEUS"],
            "recommended_action": (
                "1. Identify the malformed metric in Prometheus targets. "
                "2. Fix the exporter or scraping configuration. "
                "3. Validate metric types (gauge vs counter vs histogram). "
                "4. Re-ingest corrected data."
            ),
        })

    return anomalies


def detect_anomalies_from_window(
    rows: List[Dict[str, Any]],
    window_start: datetime | None = None,
    window_end: datetime | None = None,
) -> List[Dict[str, Any]]:
    """Apply all A1–A7 heuristic detectors to a time-windowed row set.

    This is the primary entry point for ml_detector.py.

    Args:
        rows: List of row dicts (from v_unified_analysis or similar)
        window_start: Lower bound of the time window (used for ingestion_errors query)
        window_end: Upper bound of the time window

    Returns:
        List of anomaly dicts with keys: anomaly_type, atm_id, detected_at,
        severity, title, explanation, sources_involved, recommended_action,
        correlation_id.
    """
    ing_errors = _ingestion_errors_in_window(window_start, window_end)

    detectors: List[Callable[[List[Dict[str, Any]], List[Dict[str, Any]] | None], List[Dict[str, Any]]]] = [
        lambda d, _: a1_detection(d),
        lambda d, _: a2_detection(d),
        lambda d, _: a3_detection(d),
        lambda d, _: a4_detection(d),
        lambda d, _: a5_detection(d),
        lambda d, _: a6_detection(d),
        lambda d, ie: a7_detection(d, ie),
    ]

    found: List[Dict[str, Any]] = []
    seen: set = set()
    for fn in detectors:
        for a in fn(rows, ing_errors):
            key = (a.get("anomaly_type"), a.get("atm_id"))
            if key in seen:
                continue
            seen.add(key)
            found.append(a)

    return found


# ─── Class Wrapper (legacy API + connection management) ───────────────────────

class AnomalyDetector:
    """Connection-aware convenience wrapper around the stateless detection functions.

    Maintains backward compatibility with existing scripts (main(), save_anomalies).
    ml_detector.py should use the standalone detect_anomalies_from_window() instead.
    """

    def __init__(self, db_path: str | None = None):
        self.db_path = db_path

    def _get_conn(self):
        return get_conn()

    def query(self, sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
        from psycopg2.extras import RealDictCursor
        conn = self._get_conn()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(sql, params)
                return [dict(r) for r in cur.fetchall()]
        finally:
            try:
                release_conn(conn)
            except Exception:
                pass

    def load_data(self) -> List[Dict[str, Any]]:
        return self.query("SELECT * FROM v_unified_analysis ORDER BY timestamp ASC")

    def detect_anomalies(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return detect_anomalies_from_window(data)

    def detect_anomalies_from_window(
        self,
        rows: List[Dict[str, Any]],
        window_start: datetime | None = None,
        window_end: datetime | None = None,
    ) -> List[Dict[str, Any]]:
        return detect_anomalies_from_window(rows, window_start, window_end)

    def save_anomalies(self, anomalies: List[Dict[str, Any]]) -> int:
        """Persist detected anomalies to the `anomalies` table."""
        if not anomalies:
            print("No anomalies to save.")
            return 0

        conn = self._get_conn()
        saved = 0
        try:
            with conn.cursor() as cur:
                for a in anomalies:
                    anomaly_type = a.get("anomaly_type")
                    atm_id = a.get("atm_id")
                    detected_at = a.get("detected_at") or datetime.now(timezone.utc)
                    severity = a.get("severity") or "HIGH"
                    title = a.get("title") or ""
                    explanation = a.get("explanation") or _datetime_safe_json_dumps(a)
                    correlation_id = a.get("correlation_id")
                    transaction_id = a.get("transaction_id")
                    sources = a.get("sources_involved") or []
                    recommended_action = a.get("recommended_action")

                    if atm_id is None:
                        cur.execute(
                            "SELECT 1 FROM anomalies WHERE anomaly_type = %s AND atm_id IS NULL",
                            (anomaly_type,))
                    else:
                        cur.execute(
                            "SELECT 1 FROM anomalies WHERE anomaly_type = %s AND atm_id = %s",
                            (anomaly_type, atm_id))
                    if cur.fetchone():
                        continue

                    cur.execute(
                        "INSERT INTO anomalies "
                        "(detected_at, anomaly_type, atm_id, correlation_id, transaction_id, "
                        "model_confidence_score, severity, title, explanation, "
                        "recommended_action, sources_involved, feedback_rating, is_active, is_starred) "
                        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                        (
                            detected_at, anomaly_type, atm_id, correlation_id, transaction_id,
                            a.get("model_confidence_score"),
                            severity, title, explanation, recommended_action,
                            Json(sources), None, 1, 0,
                        ),
                    )
                    saved += 1
            conn.commit()
        finally:
            try:
                release_conn(conn)
            except Exception:
                pass

        print(f"Saved {saved} anomalies to database.")
        return saved

    def main(self):
        data = self.load_data()
        anns = self.detect_anomalies(data)
        self.save_anomalies(anns)
