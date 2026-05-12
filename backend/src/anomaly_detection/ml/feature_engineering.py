"""Feature engineering for ML anomaly detection.

Takes a time window of rows from v_unified_analysis and produces a flat
feature vector suitable for Isolation Forest and XGBoost.

Feature groups:
    Metric statistics       — mean/std/min/max/rate-of-change for key metrics
    Percentile features    — p75/p95 for JVM, OS memory, Kafka RT
    Temporal features      — linear slope over the window (trend detection)
    Event counts           — counts of ERROR/CRITICAL events per source per window
    Severity-weighted      — count of FATAL/CRITICAL events (not just presence)
    Cross-source           — whether >1 source has simultaneous anomalous signals
    Kafka health           — success rate, RT spike counts, offline flags
    Label                  — (training only) derived from _anomaly_tag field in payload

IMPORTANT: If you add/remove features, update FEATURE_NAMES count, the
FEATURE_COUNT constant, and re-run training to regenerate model artifacts.
"""
from __future__ import annotations

import json
import numpy as np
import pandas as pd
from typing import Any

FEATURE_NAMES = [
    # Metric features (14)
    "jvm_mem_mean", "jvm_mem_max", "jvm_mem_rate",
    "jvm_gc_mean", "jvm_gc_max",
    "cpu_usage_mean", "cpu_usage_max",
    "os_mem_mean", "os_mem_max", "os_mem_rate",
    "kafka_rt_mean", "kafka_rt_max",
    "kafka_sr_min",
    "container_restart_max",
    # Percentile features (9)
    "jvm_mem_p75", "jvm_mem_p95",
    "os_mem_p75", "os_mem_p95",
    "kafka_rt_p75", "kafka_rt_p90", "kafka_rt_p99",
    "cpu_usage_p90", "cpu_usage_p99",
    # Temporal/slope features (5)
    "jvm_mem_slope",
    "os_mem_slope",
    "kafka_rt_slope",
    "kafka_sr_slope",
    "cpu_usage_slope",
    # Event count features (10)
    "atm_app_error_count",
    "terminal_handler_fatal_count",
    "terminal_handler_startup_count",
    "terminal_handler_oom_count",
    "hardware_cassette_empty_count",
    "hardware_cassette_low_count",
    "kafka_offline_count",
    "kafka_null_status_count",
    "timeout_count",
    "network_disconnect_count",
    # Severity-weighted features (2)
    "fatal_critical_weighted_sum",
    "error_event_count",
    # Cross-source / anomaly flags (7)
    "sources_with_errors",
    "has_oom_event",
    "has_network_disconnect",
    "has_timeout",
    "kafka_out_of_order",
    "anomaly_tag_count",
    "atm_unique_count",
]
FEATURE_COUNT = len(FEATURE_NAMES)
assert FEATURE_COUNT == 47, f"Expected 47 features, got {FEATURE_COUNT}"


def _linear_slope(series: pd.Series) -> float:
    """Compute the linear regression slope over a series.

    Returns 0.0 if fewer than 2 non-NaN values.
    Positive = increasing trend; negative = decreasing.
    """
    vals = series.dropna()
    if len(vals) < 2:
        return 0.0
    n = len(vals)
    x = np.arange(n, dtype=float)
    y = vals.values.astype(float)
    x_mean = x.mean()
    y_mean = y.mean()
    num = float(np.sum((x - x_mean) * (y - y_mean)))
    den = float(np.sum((x - x_mean) ** 2))
    return num / den if den != 0 else 0.0


def _percentile(series: pd.Series, q: float) -> float:
    """Return the q-th percentile of a series, or 0.0 if empty."""
    vals = series.dropna()
    if vals.empty:
        return 0.0
    return float(np.percentile(vals, q))


def extract_features(rows: list[dict[str, Any]]) -> np.ndarray:
    """Extract a feature vector from a list of v_unified_analysis rows.

    Args:
        rows: List of dicts from a time-windowed query of v_unified_analysis.
              Each dict must have at least: source, metric_name, metric_value,
              event_type, severity, raw_payload.

    Returns:
        1D numpy array of shape (FEATURE_COUNT,).
    """
    df = pd.DataFrame(rows)
    if df.empty:
        return np.zeros(FEATURE_COUNT)

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
            return {"mean": 0.0, "max": 0.0, "rate": 0.0, "p75": 0.0, "p95": 0.0, "slope": 0.0}
        sorted_vals = vals.sort_index()
        rate = float(sorted_vals.iloc[-1] - sorted_vals.iloc[0]) if len(sorted_vals) > 1 else 0.0
        return {
            "mean": float(vals.mean()),
            "max": float(vals.max()),
            "rate": rate,
            "p75": _percentile(vals, 75),
            "p95": _percentile(vals, 95),
            "slope": _linear_slope(sorted_vals),
        }

    jvm_mem = metric_stats("jvm_memory_used_bytes")
    jvm_gc  = metric_stats("jvm_gc_pause_seconds_sum")

    cpu_rows = pd.concat([
        safe_float(df.loc[df["metric_name"] == "process_cpu_usage", "metric_value"]) * 100,
        safe_float(df.loc[df["metric_name"] == "container/cpu/usage_time", "metric_value"]),
    ])
    cpu_mean = float(cpu_rows.mean()) if not cpu_rows.empty else 0.0
    cpu_max  = float(cpu_rows.max())  if not cpu_rows.empty else 0.0
    cpu_p90  = _percentile(cpu_rows, 90)
    cpu_p99  = _percentile(cpu_rows, 99)
    cpu_slope = _linear_slope(cpu_rows.sort_index()) if not cpu_rows.empty else 0.0

    os_mem = metric_stats("windows_os_snapshot")

    kafka_rt_payload = df.loc[df["source"] == "KAFKA", "raw_payload"].apply(
        lambda p: parse_payload(p).get("response_time_ms", 0)
    )
    kafka_rt_payload = pd.to_numeric(kafka_rt_payload, errors="coerce").dropna()
    kafka_rt_mean = float(kafka_rt_payload.mean()) if not kafka_rt_payload.empty else 0.0
    kafka_rt_max  = float(kafka_rt_payload.max())  if not kafka_rt_payload.empty else 0.0
    kafka_rt_p75  = _percentile(kafka_rt_payload, 75)
    kafka_rt_p90  = _percentile(kafka_rt_payload, 90)
    kafka_rt_p99  = _percentile(kafka_rt_payload, 99)
    kafka_rt_slope = _linear_slope(kafka_rt_payload.sort_index()) if not kafka_rt_payload.empty else 0.0

    kafka_sr = df.loc[df["source"] == "KAFKA", "raw_payload"].apply(
        lambda p: float(parse_payload(p).get("transaction_success_rate", 100.0))
    )
    kafka_sr = pd.to_numeric(kafka_sr, errors="coerce").dropna()
    kafka_sr_min   = float(kafka_sr.min()) if not kafka_sr.empty else 100.0
    kafka_sr_slope = _linear_slope(kafka_sr.sort_index()) if len(kafka_sr) > 1 else 0.0

    restart_vals = safe_float(df.loc[df["metric_name"] == "container/restart_count", "metric_value"])
    restart_max  = float(restart_vals.max()) if not restart_vals.empty else 0.0

    atm_app = df[df["source"] == "ATM_APP"]
    th      = df[df["source"] == "TERMINAL_HANDLER"]
    hw      = df[df["source"] == "HARDWARE"]
    kafka_df= df[df["source"] == "KAFKA"]

    atm_app_errors       = int(((atm_app["severity"] == "ERROR") | (atm_app["severity"] == "CRITICAL")).sum())
    atm_app_errors_all   = int(((atm_app["severity"] == "ERROR") | (atm_app["severity"] == "CRITICAL") | (atm_app["severity"] == "WARNING")).sum())
    th_fatals           = int((th["severity"] == "FATAL").sum())
    th_startups         = int((th["event_type"] == "STARTUP").sum())
    th_oom              = int((th["event_type"] == "OOM_ERROR").sum())
    hw_cassette_empty   = int((hw["event_type"] == "CASSETTE_EMPTY").sum())
    hw_cassette_low     = int((hw["event_type"] == "CASSETTE_LOW").sum())

    kafka_offline = int(kafka_df["raw_payload"].apply(
        lambda p: parse_payload(p).get("atm_status") == "Offline"
    ).sum())
    kafka_null_status = int(kafka_df["raw_payload"].apply(
        lambda p: parse_payload(p).get("atm_status") is None
    ).sum())

    timeout_count = int((df["event_type"] == "TIMEOUT").sum())
    network_disconnect_count = int((atm_app["event_type"] == "NETWORK_DISCONNECT").sum())

    fatal_critical_weighted = th_fatals * 3 + atm_app_errors * 2

    error_sources = set()
    if atm_app_errors > 0:      error_sources.add("ATM_APP")
    if th_fatals > 0:           error_sources.add("TERMINAL_HANDLER")
    if hw_cassette_empty > 0:  error_sources.add("HARDWARE")
    if kafka_offline > 0:       error_sources.add("KAFKA")

    has_oom              = int((th["event_type"] == "OOM_ERROR").any())
    has_network_disconnect = int((atm_app["event_type"] == "NETWORK_DISCONNECT").any())
    has_timeout          = int((df["event_type"] == "TIMEOUT").any())

    kafka_oo = int(kafka_df["raw_payload"].apply(
        lambda p: parse_payload(p).get("_anomaly_tag") == "A7_OUT_OF_ORDER"
    ).any())

    anomaly_tag_count = int(df["raw_payload"].apply(
        lambda p: bool(parse_payload(p).get("_anomaly_tag"))
    ).sum())

    atm_unique_count = int(df["atm_id"].dropna().nunique())

    return np.array([
        # Metric features (14)
        jvm_mem["mean"], jvm_mem["max"], jvm_mem["rate"],
        jvm_gc["mean"], jvm_gc["max"],
        cpu_mean, cpu_max,
        os_mem["mean"], os_mem["max"], os_mem["rate"],
        kafka_rt_mean, kafka_rt_max,
        kafka_sr_min,
        restart_max,
        # Percentile features (9)
        jvm_mem["p75"], jvm_mem["p95"],
        os_mem["p75"], os_mem["p95"],
        kafka_rt_p75, kafka_rt_p90, kafka_rt_p99,
        cpu_p90, cpu_p99,
        # Temporal/slope features (5)
        jvm_mem["slope"],
        os_mem["slope"],
        kafka_rt_slope,
        kafka_sr_slope,
        cpu_slope,
        # Event count features (10)
        atm_app_errors,
        th_fatals, th_startups, th_oom,
        hw_cassette_empty, hw_cassette_low,
        kafka_offline, kafka_null_status,
        timeout_count,
        network_disconnect_count,
        # Severity-weighted features (2)
        fatal_critical_weighted,
        atm_app_errors_all,
        # Cross-source / anomaly flags (7)
        len(error_sources),
        has_oom, has_network_disconnect, has_timeout, kafka_oo,
        anomaly_tag_count,
        atm_unique_count,
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
