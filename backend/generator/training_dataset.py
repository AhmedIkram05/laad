"""One-time training dataset generator.

Generates a synthetic JSON dataset containing all 7 anomaly types (A1-A7)
with realistic baseline data, suitable for offline ML model training.

Usage:
    python -m backend.generator.training_dataset

Output:
    backend/src/anomaly_detection/ml/training_data.json
    (~100-200MB depending on hours generated)
"""
from __future__ import annotations

import json
import random
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from backend.generator.config import ATMS, ATM_LOCATIONS

OUTPUT_PATH = Path(__file__).parent.parent / "src" / "anomaly_detection" / "ml" / "artifacts" / "training_data.json"
DURATION_HOURS = 24
TICK_SECONDS = 1

def _payload(overrides: dict) -> dict:
    base = {"location_code": "GB-LDN-001"}
    base.update(overrides)
    return base

def _metric(name: str, value: float, timestamp: datetime, source: str, atm_id: str, payload: dict) -> dict:
    return {
        "timestamp": timestamp.isoformat(),
        "source": source,
        "atm_id": atm_id,
        "metric_name": name,
        "metric_value": value,
        "event_type": None,
        "severity": None,
        "raw_payload": json.dumps(payload),
    }

def _event(timestamp: datetime, source: str, atm_id: str, event_type: str, severity: str, message: str, payload: dict) -> dict:
    return {
        "timestamp": timestamp.isoformat(),
        "source": source,
        "atm_id": atm_id,
        "metric_name": None,
        "metric_value": None,
        "event_type": event_type,
        "severity": severity,
        "message": message,
        "raw_payload": json.dumps(payload),
    }

def generate_baseline(t: datetime, atm: str, rng: random.Random) -> list[dict]:
    rows = []
    loc = ATM_LOCATIONS.get(atm, "GB-LDN-001")
    jvm_mem = 80_000_000 + rng.gauss(0, 5_000_000)
    gc_pause = rng.uniform(0.01, 0.3)
    cpu = rng.uniform(15, 45)
    os_mem = rng.uniform(30, 65)
    kafka_rt = rng.uniform(50, 250)
    kafka_sr = rng.uniform(95, 100)
    rows.append(_metric("jvm_memory_used_bytes", jvm_mem, t, "PROMETHEUS", atm, _payload({"atm_id": atm, "location_code": loc})))
    rows.append(_metric("jvm_gc_pause_seconds_sum", gc_pause, t, "PROMETHEUS", atm, _payload({"atm_id": atm})))
    rows.append(_metric("process_cpu_usage", cpu / 100, t, "PROMETHEUS", atm, _payload({"atm_id": atm})))
    rows.append(_metric("container/cpu/usage_time", cpu, t, "CLOUD", atm, _payload({"atm_id": atm, "location_code": loc})))
    rows.append(_metric("container/restart_count", rng.randint(0, 1), t, "CLOUD", atm, _payload({"atm_id": atm})))
    rows.append(_metric("windows_os_snapshot", os_mem, t, "OS", atm, _payload({"atm_id": atm, "location_code": loc})))
    rows.append(_event(t, "ATM_APP", atm, "HEARTBEAT", "INFO", "ATM operational", _payload({"atm_id": atm, "location_code": loc})))
    rows.append(_event(t, "KAFKA", atm, "METRIC", "INFO", "Latency update", _payload({"atm_id": atm, "response_time_ms": round(kafka_rt, 1), "transaction_success_rate": round(kafka_sr, 2), "atm_id": atm})))
    rows.append(_event(t, "TERMINAL_HANDLER", atm, "HEARTBEAT", "INFO", "Pod healthy", _payload({"atm_id": atm, "pod_name": f"th-{atm.lower()}-1"})))
    rows.append(_event(t, "HARDWARE", atm, "SENSOR", "INFO", "Cassette nominal", _payload({"atm_id": atm})))
    return rows

def inject_a1(rows: list[dict], t: datetime, atm: str, corr_id: str) -> None:
    loc = ATM_LOCATIONS.get(atm, "GB-LDN-001")
    times = [t, t+timedelta(seconds=5), t+timedelta(seconds=10), t+timedelta(seconds=15)]
    for i, (src, evt, sev, msg, p) in enumerate([
        ("ATM_APP", "NETWORK_DISCONNECT", "ERROR", "Network connection lost", {"_anomaly_tag": "A1", "location_code": loc}),
        ("ATM_APP", "TIMEOUT", "ERROR", "Request timed out", {"_anomaly_tag": "A1"}),
        ("KAFKA", "STATUS", "INFO", "ATM Offline", {"_anomaly_tag": "A1", "atm_status": "Offline"}),
        ("TERMINAL_HANDLER", "NETWORK_ERROR", "FATAL", "Connection timed out", {"_anomaly_tag": "A1"}),
    ]):
        rows.append(_event(times[i], src, atm, evt, sev, msg, p | {"correlation_id": corr_id, "atm_id": atm}))

def inject_a2(rows: list[dict], t: datetime, atm: str, corr_id: str) -> None:
    for i, (src, evt, sev, msg, p) in enumerate([
        ("HARDWARE", "CASSETTE_LOW", "WARNING", "Cash low in cassette 1", {"_anomaly_tag": "A2"}),
        ("HARDWARE", "CASSETTE_EMPTY", "CRITICAL", "Cash empty in cassette 1", {"_anomaly_tag": "A2"}),
        ("KAFKA", "STATUS", "INFO", "ATM Out of Service", {"_anomaly_tag": "A2", "atm_status": "OutOfService"}),
    ]):
        rows.append(_event(t + timedelta(minutes=i*5), src, atm, evt, sev, msg, p | {"correlation_id": corr_id, "atm_id": atm}))

def inject_a3(rows: list[dict], t: datetime, atm: str, corr_id: str) -> None:
    loc = ATM_LOCATIONS.get(atm, "GB-LDN-001")
    for i in range(90):
        tick_t = t + timedelta(minutes=i)
        jvm_mem = 1e8 + (i * 1e7) + random.gauss(0, 1e6)
        gc_pause = min(5.0, i * 0.05) + random.gauss(0, 0.1)
        cpu_usage = min(95.0, 20 + (i * 0.8)) + random.gauss(0, 2)
        rows.append(_metric("jvm_memory_used_bytes", jvm_mem, tick_t, "PROMETHEUS", atm, {"_anomaly_tag": "A3", "correlation_id": corr_id, "atm_id": atm, "location_code": loc}))
        rows.append(_metric("jvm_gc_pause_seconds_sum", max(0, gc_pause), tick_t, "PROMETHEUS", atm, {"_anomaly_tag": "A3", "correlation_id": corr_id}))
        rows.append(_metric("container/cpu/usage_time", max(0, cpu_usage), tick_t, "CLOUD", atm, {"_anomaly_tag": "A3", "correlation_id": corr_id, "atm_id": atm}))
    rows.append(_event(t + timedelta(minutes=90), "TERMINAL_HANDLER", atm, "OOM_ERROR", "FATAL", "Java heap space", {"_anomaly_tag": "A3", "correlation_id": corr_id, "atm_id": atm}))

def inject_a4(rows: list[dict], t: datetime, atm: str, corr_id: str) -> None:
    pod = f"th-{atm.lower()}-{random.randint(1,3)}"
    for i, (evt, sev, msg) in enumerate([
        ("STARTUP", "INFO", "Pod starting"),
        ("CRASH", "ERROR", "Unexpected exit"),
        ("STARTUP", "INFO", "Pod restarting"),
        ("CRASH", "ERROR", "Unexpected exit"),
    ]):
        rows.append(_event(t + timedelta(seconds=i*30), "TERMINAL_HANDLER", atm, evt, sev, msg, {"_anomaly_tag": "A4", "correlation_id": corr_id, "atm_id": atm, "pod_name": pod}))
    rows.append(_metric("container/restart_count", 2, t + timedelta(minutes=2), "CLOUD", atm, {"_anomaly_tag": "A4", "correlation_id": corr_id, "atm_id": atm}))

def inject_a5(rows: list[dict], t: datetime, atm: str, corr_id: str) -> None:
    success_rate = 1.0
    for i in range(10):
        tick_t = t + timedelta(seconds=i*10)
        success_rate = max(0.3, success_rate - random.uniform(0.05, 0.15))
        rt = 5000 + random.randint(0, 1000)
        rows.append(_event(tick_t, "KAFKA", atm, "METRIC", "INFO", "Latency update", {"_anomaly_tag": "A5", "response_time_ms": rt, "success_rate": round(success_rate, 3), "correlation_id": corr_id, "atm_id": atm}))
    rows.append(_event(t + timedelta(seconds=90), "KAFKA", atm, "STATUS", "WARNING", "Success rate drop detected", {"_anomaly_tag": "A5", "success_rate": round(success_rate, 3), "correlation_id": corr_id, "atm_id": atm}))

def inject_a6(rows: list[dict], t: datetime, atm: str, corr_id: str) -> None:
    loc = ATM_LOCATIONS.get(atm, "GB-LDN-001")
    import random as _rng
    for i in range(120):
        tick_t = t + timedelta(minutes=i, seconds=_rng.randint(0, 30))
        os_mem = 20 + (i * 1.2) + _rng.gauss(0, 1)
        rows.append(_metric("windows_os_snapshot", max(0, os_mem), tick_t, "OS", atm, {"_anomaly_tag": "A6", "correlation_id": corr_id, "atm_id": atm, "location_code": loc}))
        tick_t2 = t + timedelta(minutes=i, seconds=_rng.randint(31, 59))
        os_mem2 = 20 + (i * 1.2) + _rng.gauss(0, 1)
        rows.append(_metric("windows_os_snapshot", max(0, os_mem2), tick_t2, "OS", atm, {"_anomaly_tag": "A6", "correlation_id": corr_id, "atm_id": atm}))
    rows.append(_event(t + timedelta(minutes=120), "ATM_APP", atm, "TIMEOUT", "ERROR", "OS resource timeout", {"_anomaly_tag": "A6", "correlation_id": corr_id, "atm_id": atm}))

def inject_a7(rows: list[dict], t: datetime, atm: str, corr_id: str = None) -> None:
    for i in range(5):
        offset = -1 if i % 2 == 0 else random.randint(1, 1000)
        rows.append(_event(t + timedelta(seconds=i*5), "KAFKA", atm, "METRIC", "INFO", "Malformed event", {"_anomaly_tag": "A7_OUT_OF_ORDER", "offset": offset, "correlation_id": corr_id or str(uuid.uuid4()), "atm_id": atm}))

ANOMALY_INJECTORS = {
    "A1": inject_a1,
    "A2": inject_a2,
    "A3": inject_a3,
    "A4": inject_a4,
    "A5": inject_a5,
    "A6": inject_a6,
    "A7": inject_a7,
}
ANOMALY_COOLDOWNS = {"A1": 300, "A2": 600, "A3": 3600, "A4": 300, "A5": 300, "A6": 3600, "A7": 300}

def generate(hours: int = 24) -> list[dict]:
    rng = random.Random(42)
    start = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    end = start + timedelta(hours=hours)
    rows: list[dict] = []
    anomaly_last: dict[str, datetime] = {}
    t = start
    total_ticks = int(hours * 3600 / TICK_SECONDS)
    tick = 0

    schedule = []
    for a_type in ["A1", "A2", "A3", "A4", "A5", "A6", "A7"]:
        for offset_h in range(0, hours, 3):
            schedule.append((start + timedelta(hours=offset_h + rng.random(), seconds=rng.randint(0, 3600)), a_type))
    schedule.sort(key=lambda x: x[0])
    schedule_idx = 0

    print(f"Generating {hours}h of training data ({total_ticks:,} ticks)...")
    print(f"Scheduled anomalies: {len(schedule)}")

    while t < end:
        atm = rng.choice(ATMS)
        for r in generate_baseline(t, atm, rng):
            rows.append(r)
        while schedule_idx < len(schedule) and schedule[schedule_idx][0] <= t:
            sched_t, a_type = schedule[schedule_idx]
            if (t - anomaly_last.get(a_type, datetime.min.replace(tzinfo=timezone.utc))).total_seconds() >= ANOMALY_COOLDOWNS[a_type]:
                ANOMALY_INJECTORS[a_type](rows, sched_t, atm, str(uuid.uuid4()) if a_type != "A7" else None)
                anomaly_last[a_type] = sched_t
                print(f"  [{tick}/{total_ticks}] Injected {a_type} at {sched_t.isoformat()}")
            schedule_idx += 1
        t += timedelta(seconds=TICK_SECONDS)
        tick += 1
        if tick % 3600 == 0:
            print(f"  Progress: {tick//3600}h / {hours}h ({len(rows):,} rows, {len(anomaly_last)} types injected)")

    print(f"Dataset complete: {len(rows):,} rows, {len(anomaly_last)} types")
    return rows

def main() -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    rows = generate(DURATION_HOURS)
    OUTPUT_PATH.write_text(json.dumps(rows))
    size_mb = OUTPUT_PATH.stat().st_size / 1e6
    print(f"Saved to {OUTPUT_PATH} ({size_mb:.1f} MB)")

if __name__ == "__main__":
    main()