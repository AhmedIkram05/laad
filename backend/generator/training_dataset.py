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
DURATION_HOURS = 6
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
    jvm_mem = 80_000_000 + rng.gauss(0, 2_000_000)
    gc_pause = rng.uniform(0.02, 0.15)
    cpu = rng.uniform(18, 38)
    os_mem = rng.uniform(35, 55)
    network_err = rng.randint(0, 1)
    kafka_rt = rng.uniform(60, 200)
    kafka_sr = rng.uniform(97, 100)
    rows.append(_metric("jvm_memory_used_bytes", jvm_mem, t, "PROMETHEUS", atm, _payload({"atm_id": atm, "location_code": loc})))
    rows.append(_metric("jvm_gc_pause_seconds_sum", gc_pause, t, "PROMETHEUS", atm, _payload({"atm_id": atm})))
    rows.append(_metric("process_cpu_usage", cpu / 100, t, "PROMETHEUS", atm, _payload({"atm_id": atm})))
    rows.append(_metric("container/cpu/usage_time", cpu, t, "CLOUD", atm, _payload({"atm_id": atm, "location_code": loc})))
    rows.append(_metric("container/restart_count", rng.randint(0, 1), t, "CLOUD", atm, _payload({"atm_id": atm})))
    rows.append(_metric("memory_usage_percent", os_mem, t, "OS", atm, _payload({"atm_id": atm, "location_code": loc})))
    rows.append(_metric("network_errors", network_err, t, "OS", atm, _payload({"atm_id": atm})))
    rows.append(_metric("cpu_usage_percent", cpu, t, "OS", atm, _payload({"atm_id": atm})))
    rows.append(_event(t, "ATM_APP", atm, "HEARTBEAT", "INFO", "ATM operational", _payload({"atm_id": atm, "location_code": loc})))
    rows.append(_event(t, "KAFKA", atm, "METRIC", "INFO", "Latency update", _payload({"atm_id": atm, "response_time_ms": round(kafka_rt, 1), "transaction_success_rate": round(kafka_sr, 2)})))
    rows.append(_event(t, "TERMINAL_HANDLER", atm, "HEARTBEAT", "INFO", "Pod healthy", _payload({"atm_id": atm, "pod_name": f"th-{atm.lower()}-1"})))
    rows.append(_event(t, "HARDWARE", atm, "SENSOR", "INFO", "Cassette nominal", _payload({"atm_id": atm})))
    return rows

def inject_a1(rows: list[dict], t: datetime, atm: str, corr_id: str) -> None:
    loc = ATM_LOCATIONS.get(atm, "GB-LDN-001")
    corr_id = "corr-0030-nnet-disc-0001"

    rows.append(_event(t, "ATM_APP", atm, "NETWORK_DISCONNECT", "ERROR", "Network connection lost",
        {"_anomaly_tag": "A1", "location_code": loc, "error_code": "ERR-0040", "correlation_id": corr_id, "atm_id": atm}))
    rows.append(_event(t + timedelta(seconds=5), "ATM_APP", atm, "TIMEOUT", "ERROR", "Request timed out",
        {"_anomaly_tag": "A1", "error_code": "ERR-0040", "response_time_ms": 30000, "correlation_id": corr_id, "atm_id": atm}))
    rows.append(_event(t + timedelta(seconds=10), "KAFKA", atm, "STATUS", "INFO", "ATM Offline",
        {"_anomaly_tag": "A1", "atm_status": "Offline", "transaction_failure_reason": "HOST_UNAVAILABLE", "correlation_id": corr_id, "atm_id": atm}))
    rows.append(_event(t + timedelta(seconds=15), "TERMINAL_HANDLER", atm, "NETWORK_TIMEOUT", "FATAL", "Connection timed out",
        {"_anomaly_tag": "A1", "correlation_id": corr_id, "atm_id": atm}))

def inject_a2(rows: list[dict], t: datetime, atm: str, corr_id: str) -> None:
    rows.append(_event(t, "HARDWARE", atm, "CASSETTE_LOW", "WARNING", "Cash low in cassette 1",
        {"_anomaly_tag": "A2", "cassette_id": 1, "correlation_id": corr_id, "atm_id": atm}))
    rows.append(_event(t, "HARDWARE", atm, "CASSETTE_LOW", "WARNING", "Cash low in cassette 2",
        {"_anomaly_tag": "A2", "cassette_id": 2, "correlation_id": corr_id, "atm_id": atm}))

    rows.append(_event(t + timedelta(minutes=5), "HARDWARE", atm, "CASSETTE_EMPTY", "CRITICAL", "Cash empty in cassette 1",
        {"_anomaly_tag": "A2", "cassette_id": 1, "correlation_id": corr_id, "atm_id": atm}))
    rows.append(_event(t + timedelta(minutes=5), "HARDWARE", atm, "CASSETTE_EMPTY", "CRITICAL", "Cash empty in cassette 2",
        {"_anomaly_tag": "A2", "cassette_id": 2, "correlation_id": corr_id, "atm_id": atm}))

    rows.append(_event(t + timedelta(minutes=8), "KAFKA", atm, "STATUS", "INFO", "ATM Out of Service",
        {"_anomaly_tag": "A2", "atm_status": "Out of Service", "transaction_failure_reason": "CASH_DISPENSE_ERROR",
         "transaction_rate_tps": 0.0, "transaction_success_rate": 0.0, "correlation_id": corr_id, "atm_id": atm}))

def inject_a3(rows: list[dict], t: datetime, atm: str, corr_id: str) -> None:
    loc = ATM_LOCATIONS.get(atm, "GB-LDN-001")
    pod_name = f"th-{atm.lower()}-1"

    jvm_start = 300_000_000
    jvm_end = 1_040_000_000
    jvm_step = (jvm_end - jvm_start) / 30
    gc_start = 0.45
    gc_end = 24.7
    gc_step = (gc_end - gc_start) / 30

    for i in range(30):
        tick_t = t + timedelta(minutes=i)
        jvm_mem = jvm_start + (i * jvm_step)
        gc_pause = gc_start + (i * gc_step)
        rows.append(_metric("jvm_memory_used_bytes", jvm_mem, tick_t, "PROMETHEUS", atm,
            {"_anomaly_tag": "A3", "pod_name": pod_name, "correlation_id": corr_id, "atm_id": atm, "location_code": loc}))
        rows.append(_metric("jvm_gc_pause_seconds_sum", gc_pause, tick_t, "PROMETHEUS", atm,
            {"_anomaly_tag": "A3", "pod_name": pod_name, "correlation_id": corr_id}))
        rows.append(_metric("process_cpu_usage", 0.94, tick_t, "PROMETHEUS", atm,
            {"_anomaly_tag": "A3", "pod_name": pod_name, "correlation_id": corr_id, "atm_id": atm}))
        rows.append(_metric("container/cpu/usage_time", 94.0, tick_t, "CLOUD", atm,
            {"_anomaly_tag": "A3", "pod_name": pod_name, "correlation_id": corr_id, "atm_id": atm}))

    rows.append(_event(t + timedelta(minutes=30), "TERMINAL_HANDLER", atm, "OutOfMemoryError", "FATAL", "Java heap space",
        {"_anomaly_tag": "A3", "pod_name": pod_name, "correlation_id": corr_id, "atm_id": atm}))

def inject_a4(rows: list[dict], t: datetime, atm: str, corr_id: str) -> None:
    pod_name = f"th-{atm.lower()}-1"

    rows.append(_event(t, "TERMINAL_HANDLER", atm, "STARTUP", "INFO", "Pod starting",
        {"_anomaly_tag": "A4", "pod_name": pod_name, "container_id": "container-abc123", "correlation_id": corr_id, "atm_id": atm}))
    rows.append(_metric("container/restart_count", 1, t + timedelta(minutes=2), "CLOUD", atm,
        {"_anomaly_tag": "A4", "pod_name": pod_name, "correlation_id": corr_id, "atm_id": atm}))
    rows.append(_event(t + timedelta(minutes=2, seconds=30), "TERMINAL_HANDLER", atm, "OutOfMemoryError", "FATAL", "Java heap space",
        {"_anomaly_tag": "A4", "pod_name": pod_name, "correlation_id": corr_id, "atm_id": atm}))

    rows.append(_event(t + timedelta(minutes=3), "TERMINAL_HANDLER", atm, "STARTUP", "INFO", "Pod restarting",
        {"_anomaly_tag": "A4", "pod_name": pod_name, "container_id": "container-def456", "correlation_id": corr_id, "atm_id": atm}))
    rows.append(_metric("container/restart_count", 2, t + timedelta(minutes=4), "CLOUD", atm,
        {"_anomaly_tag": "A4", "pod_name": pod_name, "correlation_id": corr_id, "atm_id": atm}))
    rows.append(_event(t + timedelta(minutes=4), "TERMINAL_HANDLER", atm, "OutOfMemoryError", "FATAL", "Java heap space",
        {"_anomaly_tag": "A4", "pod_name": pod_name, "correlation_id": corr_id, "atm_id": atm}))

    rows.append(_event(t + timedelta(minutes=4, seconds=30), "TERMINAL_HANDLER", atm, "STARTUP", "INFO", "Pod restarting",
        {"_anomaly_tag": "A4", "pod_name": pod_name, "container_id": "container-ghi789", "correlation_id": corr_id, "atm_id": atm}))

def inject_a5(rows: list[dict], t: datetime, atm: str, corr_id: str) -> None:
    corr_ids = ["corr-0010-xxyy-aabb-1234", "corr-0011-xyzw-ccdd-5678"]

    rows.append(_event(t, "KAFKA", atm, "METRIC", "INFO", "Latency update",
        {"_anomaly_tag": "A5", "response_time_ms": 3200, "transaction_success_rate": 100, "failure_count": 0, "correlation_id": corr_ids[0], "atm_id": atm}))
    rows.append(_event(t + timedelta(seconds=10), "KAFKA", atm, "METRIC", "INFO", "Latency update",
        {"_anomaly_tag": "A5", "response_time_ms": 4500, "transaction_success_rate": 72, "failure_count": 8, "correlation_id": corr_ids[0], "atm_id": atm}))
    rows.append(_event(t + timedelta(seconds=20), "KAFKA", atm, "METRIC", "INFO", "Latency update",
        {"_anomaly_tag": "A5", "response_time_ms": 30000, "transaction_success_rate": 50, "failure_count": 14, "correlation_id": corr_ids[1], "atm_id": atm}))

    rows.append(_event(t + timedelta(seconds=25), "ATM_APP", atm, "TIMEOUT", "ERROR", "Request timed out",
        {"_anomaly_tag": "A5", "error_code": "ERR-0012", "correlation_id": corr_ids[1], "atm_id": atm}))

    rows.append(_event(t + timedelta(seconds=30), "KAFKA", atm, "STATUS", "WARNING", "Success rate drop detected",
        {"_anomaly_tag": "A5", "transaction_success_rate": 50, "failure_count": 14, "correlation_id": corr_ids[1], "atm_id": atm}))

def inject_a6(rows: list[dict], t: datetime, atm: str, corr_id: str) -> None:
    loc = ATM_LOCATIONS.get(atm, "GB-LDN-001")

    mem_start = 46.0
    mem_end = 98.75
    mem_step = (mem_end - mem_start) / 30
    net_err_start = 0
    net_err_end = 22
    net_err_step = (net_err_end - net_err_start) / 30

    for i in range(30):
        tick_t = t + timedelta(minutes=i)
        mem_val = mem_start + (i * mem_step)
        net_err_val = net_err_start + (i * net_err_step)
        cpu_val = 20 + (i * 2.383)

        rows.append(_metric("memory_usage_percent", mem_val, tick_t, "OS", atm,
            {"_anomaly_tag": "A6", "correlation_id": corr_id, "atm_id": atm, "location_code": loc}))
        rows.append(_metric("network_errors", net_err_val, tick_t, "OS", atm,
            {"_anomaly_tag": "A6", "correlation_id": corr_id}))
        rows.append(_metric("cpu_usage_percent", cpu_val, tick_t, "OS", atm,
            {"_anomaly_tag": "A6", "correlation_id": corr_id, "atm_id": atm}))

    rows.append(_event(t + timedelta(minutes=30), "ATM_APP", atm, "TIMEOUT", "ERROR", "OS resource timeout - ThreadAbortException",
        {"_anomaly_tag": "A6", "error_code": "ERR-MEM", "error_detail": "ThreadAbortException: Thread was being aborted due to memory pressure", "correlation_id": corr_id, "atm_id": atm}))

def inject_a7(rows: list[dict], t: datetime, atm: str, corr_id: str = None) -> None:
    corr_id = corr_id or str(uuid.uuid4())

    rows.append(_event(t - timedelta(minutes=5), "KAFKA", atm, "METRIC", "INFO", "Kafka metrics",
        {"_anomaly_tag": "A7_OUT_OF_ORDER", "offset": 4050, "atm_status": "Online", "transaction_rate_tps": 15.5, "correlation_id": corr_id, "atm_id": atm}))
    rows.append(_event(t, "KAFKA", atm, "METRIC", "INFO", "Kafka metrics - out of order",
        {"_anomaly_tag": "A7_OUT_OF_ORDER", "offset": 4051, "atm_status": None, "transaction_rate_tps": None, "correlation_id": corr_id, "atm_id": atm}))

    rows.append(_metric("jvm_memory_used_bytes", "890iembre", t, "PROMETHEUS", atm,
        {"_anomaly_tag": "A7_MALFORMED", "correlation_id": corr_id, "atm_id": atm}))

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

def generate(hours: int = 6, output_path: Path | None = None) -> int:
    rng = random.Random(42)
    start = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    end = start + timedelta(hours=hours)
    anomaly_last: dict[str, datetime] = {}
    t = start
    total_ticks = int(hours * 3600 / TICK_SECONDS)
    tick = 0
    row_count = 0

    schedule = []
    for a_type in ["A1", "A2", "A3", "A4", "A5", "A6", "A7"]:
        for offset_h in range(0, hours, 2):
            schedule.append((start + timedelta(hours=offset_h + rng.random(), seconds=rng.randint(0, 3600)), a_type))
    schedule.sort(key=lambda x: x[0])
    schedule_idx = 0

    print(f"Generating {hours}h of training data ({total_ticks:,} ticks)...")
    print(f"Scheduled anomalies: {len(schedule)}")

    out = output_path or OUTPUT_PATH
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as f:
        f.write("[\n")
        first_row = True

        def write_rows(buf: list[dict]) -> None:
            nonlocal first_row
            for r in buf:
                if not first_row:
                    f.write(",\n")
                first_row = False
                f.write(json.dumps(r, default=str))

        while t < end:
            buf: list[dict] = []
            for atm in ATMS:
                for r in generate_baseline(t, atm, rng):
                    buf.append(r)
            while schedule_idx < len(schedule) and schedule[schedule_idx][0] <= t:
                sched_t, a_type = schedule[schedule_idx]
                if (t - anomaly_last.get(a_type, datetime.min.replace(tzinfo=timezone.utc))).total_seconds() >= ANOMALY_COOLDOWNS[a_type]:
                    anomaly_atm = rng.choice(ATMS)
                    inject_buf: list[dict] = []
                    ANOMALY_INJECTORS[a_type](inject_buf, sched_t, anomaly_atm, str(uuid.uuid4()) if a_type != "A7" else None)
                    buf.extend(inject_buf)
                    anomaly_last[a_type] = sched_t
                    print(f"  [{tick}/{total_ticks}] Injected {a_type} at {sched_t.isoformat()} on {anomaly_atm}")
                schedule_idx += 1
            write_rows(buf)
            row_count += len(buf)
            t += timedelta(seconds=TICK_SECONDS)
            tick += 1
            if tick % 3600 == 0:
                print(f"  Progress: {tick//3600}h / {hours}h ({row_count:,} rows, {len(anomaly_last)} types injected)")

        f.write("\n]\n")

    total_mb = out.stat().st_size / 1e6
    print(f"Dataset complete: {row_count:,} rows, {total_mb:.1f} MB, {len(anomaly_last)} types injected")
    return row_count


def main() -> None:
    generate(DURATION_HOURS)
    print(f"Saved to {OUTPUT_PATH}")

if __name__ == "__main__":
    main()