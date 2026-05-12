"""Feature engineering for ML anomaly detection.

Takes a time window of rows from v_unified_analysis and produces a flat
feature vector suitable for Isolation Forest and XGBoost.

Feature groups:
    Metric statistics   — rolling mean/std/min/max/rate-of-change for key metrics
    Event counts        — counts of ERROR/CRITICAL events per source per window
    Cross-source        — whether >1 source has simultaneous anomalous signals
    Kafka health        — success rate drop, response time spike flags
    Label               — (training only) derived from _anomaly_tag field in payload
"""
from __future__ import annotations

import json
import numpy as np
import pandas as pd
from typing import Any

FEATURE_NAMES = [
    # Metric features
    "jvm_mem_mean", "jvm_mem_max", "jvm_mem_rate",
    "jvm_gc_mean", "jvm_gc_max",
    "cpu_usage_mean", "cpu_usage_max",
    "os_mem_mean", "os_mem_max", "os_mem_rate",
    "kafka_rt_mean", "kafka_rt_max",
    "kafka_sr_min",
    "container_restart_max",
    # Event features
    "atm_app_error_count",
    "terminal_handler_fatal_count",
    "terminal_handler_startup_count",
    "hardware_cassette_empty_count",
    "hardware_cassette_low_count",
    "kafka_offline_count",
    "kafka_null_status_count",
    # Cross-source
    "sources_with_errors",
    "has_oom_event",
    "has_network_disconnect",
    "has_timeout",
    "kafka_out_of_order",
]


def extract_features(rows: list[dict[str, Any]]) -> np.ndarray:
    """Extract a feature vector from a list of v_unified_analysis rows.

    Args:
        rows: List of dicts from a time-windowed query of v_unified_analysis.
              Each dict must have at least: source, metric_name, metric_value,
              event_type, severity, raw_payload.

    Returns:
        1D numpy array of shape (len(FEATURE_NAMES),).
    """
    df = pd.DataFrame(rows)
    if df.empty:
        return np.zeros(len(FEATURE_NAMES))

    def safe_float(series):
        return pd.to_numeric(series, errors="coerce")

    def parse_payload(p):
        if isinstance(p, dict):
            return p
        if isinstance(p, str):
            try:
                return json.loads(p)
            except (ValueError, TypeError):
                return {}
        return {}

    def metric_stats(name: str) -> dict[str, float]:
        vals = safe_float(df.loc[df["metric_name"] == name, "metric_value"])
        if vals.empty or vals.isna().all():
            return {"mean": 0.0, "max": 0.0, "rate": 0.0}
        rate = float(vals.iloc[-1] - vals.iloc[0]) if len(vals) > 1 else 0.0
        return {"mean": float(vals.mean()), "max": float(vals.max()), "rate": rate}

    jvm_mem = metric_stats("jvm_memory_used_bytes")
    jvm_gc  = metric_stats("jvm_gc_pause_seconds_sum")

    cpu_rows = pd.concat([
        safe_float(df.loc[df["metric_name"] == "process_cpu_usage", "metric_value"]) * 100,
        safe_float(df.loc[df["metric_name"] == "container/cpu/usage_time", "metric_value"]),
    ])
    cpu_mean = float(cpu_rows.mean()) if not cpu_rows.empty else 0.0
    cpu_max  = float(cpu_rows.max())  if not cpu_rows.empty else 0.0

    os_mem = metric_stats("windows_os_snapshot")

    kafka_rt_payload = df.loc[df["source"] == "KAFKA", "raw_payload"].apply(
        lambda p: float(parse_payload(p).get("response_time_ms", 0))
    )
    kafka_rt_mean = float(kafka_rt_payload.mean()) if not kafka_rt_payload.empty else 0.0
    kafka_rt_max  = float(kafka_rt_payload.max())  if not kafka_rt_payload.empty else 0.0

    kafka_sr = df.loc[df["source"] == "KAFKA", "raw_payload"].apply(
        lambda p: float(parse_payload(p).get("transaction_success_rate", 100.0))
    )
    kafka_sr_min = float(kafka_sr.min()) if not kafka_sr.empty else 100.0

    restart_vals = safe_float(df.loc[df["metric_name"] == "container/restart_count", "metric_value"])
    restart_max  = float(restart_vals.max()) if not restart_vals.empty else 0.0

    atm_app = df[df["source"] == "ATM_APP"]
    th      = df[df["source"] == "TERMINAL_HANDLER"]
    hw      = df[df["source"] == "HARDWARE"]
    kafka_df= df[df["source"] == "KAFKA"]

    atm_app_errors       = int(((atm_app["severity"] == "ERROR") | (atm_app["severity"] == "CRITICAL")).sum())
    th_fatals            = int((th["severity"] == "FATAL").sum())
    th_startups          = int((th["event_type"] == "STARTUP").sum())
    hw_cassette_empty    = int((hw["event_type"] == "CASSETTE_EMPTY").sum())
    hw_cassette_low      = int((hw["event_type"] == "CASSETTE_LOW").sum())

    kafka_offline = int(kafka_df["raw_payload"].apply(
        lambda p: parse_payload(p).get("atm_status") == "Offline"
    ).sum())
    kafka_null_status = int(kafka_df["raw_payload"].apply(
        lambda p: parse_payload(p).get("atm_status") is None
    ).sum())

    error_sources = set()
    if atm_app_errors > 0:     error_sources.add("ATM_APP")
    if th_fatals > 0:          error_sources.add("TERMINAL_HANDLER")
    if hw_cassette_empty > 0:  error_sources.add("HARDWARE")
    if kafka_offline > 0:      error_sources.add("KAFKA")

    has_oom              = int((th["event_type"] == "OOM_ERROR").any())
    has_network_disconnect = int((atm_app["event_type"] == "NETWORK_DISCONNECT").any())
    has_timeout          = int((df["event_type"] == "TIMEOUT").any())

    kafka_oo = int(kafka_df["raw_payload"].apply(
        lambda p: parse_payload(p).get("_anomaly_tag") == "A7_OUT_OF_ORDER"
    ).any())

    return np.array([
        jvm_mem["mean"], jvm_mem["max"], jvm_mem["rate"],
        jvm_gc["mean"], jvm_gc["max"],
        cpu_mean, cpu_max,
        os_mem["mean"], os_mem["max"], os_mem["rate"],
        kafka_rt_mean, kafka_rt_max,
        kafka_sr_min,
        restart_max,
        atm_app_errors,
        th_fatals, th_startups,
        hw_cassette_empty, hw_cassette_low,
        kafka_offline, kafka_null_status,
        len(error_sources),
        has_oom, has_network_disconnect, has_timeout, kafka_oo,
    ], dtype=np.float32)


def extract_label(rows: list[dict[str, Any]]) -> str | None:
    """Extract ground-truth anomaly label from _anomaly_tag in payloads (training only).

    Returns the dominant anomaly type ('A1'–'A7') or None for normal windows.
    """
    labels = []
    for r in rows:
        raw = r.get("raw_payload") or r.get("payload")
        if not raw:
            continue
        try:
            p = json.loads(raw) if isinstance(raw, str) else raw
            tag = p.get("_anomaly_tag") or p.get("_anomaly")
            if tag and isinstance(tag, str) and len(tag) >= 2 and tag[0] == "A" and tag[1].isdigit() and tag[:2] in {"A1","A2","A3","A4","A5","A6","A7"}:
                labels.append(tag[:2])
        except Exception:
            continue
    if not labels:
        return None
    return max(set(labels), key=labels.count)