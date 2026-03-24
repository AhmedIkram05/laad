"""Custom synthetic data generator.

Creates correlated, monotonic, and small synthetic datasets for the 7
ingestion sources based on the A1-A7 anomaly scenarios defined in the guide.

The generated files (JSON/CSV) will be written to the output directory.
"""
from __future__ import annotations

import csv
import json
import os
import random
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from typing import List

from backend.ingestion.parsers.prometheus import PROMETHEUS_HEADERS
from backend.ingestion.parsers.windows_os import WINDOWS_HEADERS
from backend.ingestion.parsers.gcp_cloud_metrics import GCP_HEADERS

OUTPUT_DIR = "custom_synthetic_data_sources"
SEED = 12345
random.seed(SEED)

# Generator defaults
# This is the time of day the data generation starts
BASE_DATE = datetime.now(timezone.utc).replace(hour=8, minute=0, second=0, microsecond=0)
# and number of hours to generate data for
HOURS = 24

# Fixed ATM fleet matching guide (GB = Great Britain)
ATMS = ["ATM-GB-0001", "ATM-GB-0002", "ATM-GB-0003", "ATM-GB-0004"]

# Physical ATM Locations
ATM_LOCATIONS = {
    "ATM-GB-0001": "LOC-001",
    "ATM-GB-0002": "LOC-002",
    "ATM-GB-0003": "LOC-003",
    "ATM-GB-0004": "LOC-004",
}

# Scenario-level shared keys - from guide or consistent defaults
SCENARIO_CORR = {
    "A1": "corr-0030-nnet-disc-0001",
    "A2": "corr-a002-cash-depl-0001",
    "A5": "corr-0010-xxyy-aabb-1234",
    "A5_2": "corr-0011-xyzw-ccdd-5678",
}
POD_NAME = "terminal-handler-pod-0"
OS_VERSION = "Windows-Server-2019"


def ts(dt: datetime) -> str:
    return dt.isoformat()


def minutes_range(start: datetime, end: datetime, step_minutes: int = 1):
    current = start
    while current < end:
        yield current
        current += timedelta(minutes=step_minutes)


def make_corr() -> str:
    return f"corr-{str(uuid4())[:12]}"


def make_txn() -> str:
    return f"txn-{str(uuid4())[:12]}"


def ensure_output(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def build_atm_app_log(start: datetime, end: datetime) -> List[dict]:
    records = []
    for t in minutes_range(start, end, step_minutes=1):
        for atm in ATMS:
            # Each minute has a 40% chance of a transaction record
            if random.random() < 0.4:
                record = {
                    "timestamp": ts(t),
                    "log_level": "INFO",
                    "atm_id": atm,
                    "location_code": ATM_LOCATIONS[atm],
                    "event_type": "TRANSACTION_END",
                    "message": "Transaction completed",
                    "component": "TransactionManager",
                    "response_time_ms": random.randint(100, 1200),
                    "correlation_id": make_corr() if random.random() < 0.3 else None,
                    "transaction_id": make_txn(),
                    "error_code": None,
                    "error_detail": None,
                    "_anomaly": None,
                }
                records.append(record)
    return records


def build_hardware_log(start: datetime, end: datetime) -> List[dict]:
    rows = []
    for t in minutes_range(start, end, step_minutes=1):
        for atm in ATMS:
            # Heartbeat/Status every minute with 10% chance of a status event
            if random.random() < 0.1:
                rows.append({
                    "timestamp": ts(t),
                    "atm_id": atm,
                    "component": "CASH_DISPENSER",
                    "event_type": "CASSETTE_OK",
                    "severity": "INFO",
                    "message": "Cassette status nominal",
                    "metric_name": "CASSETTE_LEVEL",
                    "metric_value": 50,
                    "correlation_id": None,
                    "_anomaly": None,
                })
    return rows


def build_terminal_handler_log(start: datetime, end: datetime) -> List[dict]:
    rows = []
    for t in minutes_range(start, end, step_minutes=1):
        # 30% chance of a handler event per minute
        if random.random() < 0.3:
            rows.append({
                "timestamp": ts(t),
                "log_level": "INFO",
                "service_name": "terminal-handler-sim",
                "service_version": "0.1.0",
                "event_type": "REQUEST_HANDLED",
                "message": "Handled incoming request",
                "correlation_id": make_corr(),
                "transaction_id": make_txn(),
                "atm_id": random.choice(ATMS),
                "pod_name": POD_NAME,
                "container_id": "container-main",
                "exception_class": None,
                "_anomaly": None,
            })
    return rows


def build_kafka_stream(start: datetime, end: datetime) -> List[dict]:
    rows = []
    offset = 1000
    for t in minutes_range(start, end, step_minutes=1):
        for atm in ATMS:
            # Each minute has a 40% chance of a transaction event
            if random.random() < 0.4:
                rows.append({
                    "timestamp": ts(t),
                    "event_id": f"evt-{offset}",
                    "atm_id": atm,
                    "atm_status": "Online",
                    "transaction_rate_tps": round(random.uniform(0.1, 2.0), 2),
                    "response_time_ms": random.randint(50, 500),
                    "transaction_volume": random.randint(0, 20),
                    "transaction_success_rate": 100.0,
                    "transaction_failure_reason": None,
                    "failure_count": 0,
                    "correlation_id": make_corr(),
                    "kafka_offset": offset,
                    "_anomaly": None,
                })
                offset += 1
    return rows


def build_prometheus_metrics(start: datetime, end: datetime) -> List[dict]:
    rows = []
    for t in minutes_range(start, end, step_minutes=1):
        # Baseline metrics
        for name, base_val in [("jvm_memory_used_bytes", 300_000_000), ("jvm_gc_pause_seconds_sum", 0.1), ("process_cpu_usage", 0.2)]:
            rows.append({
                "timestamp": ts(t),
                "metric_name": name,
                "metric_type": "gauge",
                "metric_value": base_val + random.randint(-1000, 1000) if "bytes" in name else base_val + random.uniform(-0.01, 0.01),
                "service_name": "terminal-handler-sim",
                "pod_name": POD_NAME,
                "container_id": "container-main",
                "label_area": "payments",
                "label_env": "staging",
                "help_text": "",
                "_anomaly": None,
            })
    return rows


def build_windows_os_metrics(start: datetime, end: datetime) -> List[dict]:
    rows = []
    for t in minutes_range(start, end, step_minutes=1):
        for atm in ATMS:
            total = 4096
            used = random.randint(400, 1500)
            cpu = round(random.uniform(5.0, 40.0), 2)
            mem_pct = round((used / total) * 100.0, 2)
            rows.append({
                "timestamp": ts(t),
                "atm_id": atm,
                "hostname": f"host-{atm.lower()}",
                "os_version": OS_VERSION,
                "cpu_usage_percent": cpu,
                "memory_used_mb": used,
                "memory_total_mb": total,
                "memory_usage_percent": mem_pct,
                "disk_read_bytes_per_sec": round(random.uniform(0, 5000), 2),
                "disk_write_bytes_per_sec": round(random.uniform(0, 5000), 2),
                "disk_free_gb": round(random.uniform(10.0, 200.0), 2),
                "network_bytes_sent_per_sec": round(random.uniform(0, 10000), 2),
                "network_bytes_recv_per_sec": round(random.uniform(0, 10000), 2),
                "network_errors": 0,
                "process_count": random.randint(80, 120),
                "system_uptime_seconds": int(random.uniform(3600, 86400)),
                "event_log_errors_last_min": 0,
                "_anomaly": None,
            })
    return rows


def build_gcp_metrics(start: datetime, end: datetime) -> List[dict]:
    rows = []
    for t in minutes_range(start, end, step_minutes=1):
        rows.append({
            "timestamp": ts(t),
            "project_id": "custom-sim",
            "resource_type": "gke_container",
            "resource_id": f"container-{random.randint(1000,9999)}",
            "zone": "europe-west1-b",
            "metric_name": "container/cpu/usage_time",
            "metric_value": round(random.uniform(10.0, 30.0), 2),
            "metric_unit": "%",
            "cpu_usage_percent": round(random.uniform(1.0, 90.0), 2),
            "memory_usage_bytes": random.randint(100_000_000, 800_000_000),
            "memory_limit_bytes": 1024_000_000,
            "network_ingress_bytes": random.randint(1000, 100000),
            "network_egress_bytes": random.randint(1000, 100000),
            "restart_count": 0,
            "pod_name": POD_NAME,
            "label_app": "custom",
            "label_env": "staging",
            "label_version": "0.1",
            "_anomaly": None,
        })
    return rows


def write_json(data: List[dict], filename: str, outdir: str) -> None:
    path = os.path.join(outdir, filename)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, default=str)
    print(f"  Written {len(data)} records → {path}")


def write_csv(rows: List[dict], fieldnames: List[str], filename: str, outdir: str) -> None:
    path = os.path.join(outdir, filename)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for r in rows:
            writer.writerow(r)
    print(f"  Written {len(rows)} rows → {path}")


# --- ANOMALY INJECTION FUNCTIONS (A1-A7) ---

def inject_a1_network_timeout_cascade(atm_app, kafka, terminal, t0):
    """
    A1: Network Timeout Cascade (ATM-GB-0003, 10:00)
    Sources: ATM App Log, Kafka Stream, Terminal Handler Log
    """
    corr = SCENARIO_CORR["A1"]
    atm = "ATM-GB-0003"
    
    # ATM App Log: DISCONNECT then TIMEOUT
    atm_app.append({
        "timestamp": ts(t0),
        "log_level": "ERROR",
        "atm_id": atm,
        "location_code": ATM_LOCATIONS[atm],
        "event_type": "NETWORK_DISCONNECT",
        "message": "TCP Connection lost",
        "component": "NetworkClient",
        "error_code": "ERR-0040",
        "correlation_id": corr,
        "_anomaly": "A1_DISCONNECT",
    })
    atm_app.append({
        "timestamp": ts(t0 + timedelta(minutes=1)),
        "log_level": "ERROR",
        "atm_id": atm,
        "location_code": ATM_LOCATIONS[atm],
        "event_type": "TIMEOUT",
        "message": "Host response timeout",
        "component": "NetworkClient",
        "response_time_ms": 30000,
        "error_code": "ERR-0012",
        "correlation_id": corr,
        "_anomaly": "A1_TIMEOUT",
    })
    
    # Kafka: Offline
    kafka.append({
        "timestamp": ts(t0 + timedelta(minutes=1)),
        "event_id": f"evt-a1-offline",
        "atm_id": atm,
        "atm_status": "Offline",
        "transaction_rate_tps": 0.0,
        "response_time_ms": 30000,
        "transaction_success_rate": 0.0,
        "transaction_failure_reason": "HOST_UNAVAILABLE",
        "correlation_id": corr,
        "_anomaly": "A1_KAFKA_OFFLINE",
    })
    
    # Terminal Handler: NETWORK_TIMEOUT
    terminal.append({
        "timestamp": ts(t0 + timedelta(minutes=2)),
        "log_level": "ERROR",
        "service_name": "terminal-handler-sim",
        "event_type": "NETWORK_TIMEOUT",
        "message": f"Connection timed out for {atm}",
        "correlation_id": corr,
        "atm_id": atm,
        "pod_name": POD_NAME,
        "_anomaly": "A1_HANDLER_TIMEOUT",
    })


def inject_a2_cassette_depletion(hardware, kafka, t0):
    """
    A2: Cash Cassette Depletion -> Out of Service (ATM-GB-0003, 09:00-09:59)
    Sources: ATM Hardware Sensor Log, Kafka Stream
    """
    corr = SCENARIO_CORR["A2"]
    atm = "ATM-GB-0003"
    
    # Hardware escalation
    for m in [0, 15]:
        hardware.append({
            "timestamp": ts(t0 + timedelta(minutes=m)),
            "atm_id": atm,
            "component": "CASH_DISPENSER",
            "event_type": "CASSETTE_LOW",
            "severity": "WARNING",
            "metric_name": "CASSETTE_LEVEL",
            "metric_value": 10,
            "correlation_id": corr,
            "_anomaly": "A2_LOW",
        })
    for m in [45, 59]:
        hardware.append({
            "timestamp": ts(t0 + timedelta(minutes=m)),
            "atm_id": atm,
            "component": "CASH_DISPENSER",
            "event_type": "CASSETTE_EMPTY",
            "severity": "CRITICAL",
            "metric_name": "CASSETTE_LEVEL",
            "metric_value": 0,
            "correlation_id": corr,
            "_anomaly": "A2_EMPTY",
        })
        
    # Kafka: Out of Service
    kafka.append({
        "timestamp": ts(t0 + timedelta(minutes=59)),
        "atm_id": atm,
        "atm_status": "Out of Service",
        "transaction_rate_tps": 0.0,
        "transaction_success_rate": 0.0,
        "transaction_failure_reason": "CASH_DISPENSE_ERROR",
        "correlation_id": corr,
        "_anomaly": "A2_KAFKA_OOS",
    })


def inject_a3_jvm_memory_leak(prometheus, gcp, terminal, t0):
    """
    A3: JVM Memory Leak -> OOM (Terminal Handler, 08:00-09:30)
    Sources: Prometheus Metrics, GCP Cloud Metrics, Terminal Handler App Log
    """
    for i in range(10):
        t = t0 + timedelta(minutes=i*10)
        # Prometheus monotonic rise
        prometheus.append({
            "timestamp": ts(t),
            "metric_name": "jvm_memory_used_bytes",
            "metric_value": 300_000_000 + (740_000_000 * i // 9),
            "pod_name": POD_NAME,
            "service_name": "terminal-handler-sim",
            "_anomaly": "A3_LEAK",
        })
        prometheus.append({
            "timestamp": ts(t),
            "metric_name": "jvm_gc_pause_seconds_sum",
            "metric_value": round(0.45 + (24.25 * i / 9), 2),
            "pod_name": POD_NAME,
            "_anomaly": "A3_GC",
        })
        # GCP CPU rise
        gcp.append({
            "timestamp": ts(t),
            "project_id": "custom-sim",
            "resource_type": "gke_container",
            "resource_id": f"container-{random.randint(1000,9999)}",
            "zone": "europe-west1-b",
            "metric_name": "container/cpu/usage_time",
            "metric_value": round(20.0 + (74.0 * i / 9), 2),
            "metric_unit": "%",
            "cpu_usage_percent": round(20.0 + (74.0 * i / 9), 2),
            "pod_name": POD_NAME,
            "_anomaly": "A3_GCP_CPU",
        })
    
    # Terminal Handler: OOM FATAL
    terminal.append({
        "timestamp": ts(t0 + timedelta(minutes=90)),
        "log_level": "FATAL",
        "event_type": "OOM_ERROR",
        "exception_class": "OutOfMemoryError",
        "message": "Java heap space",
        "pod_name": POD_NAME,
        "_anomaly": "A3_FATAL",
    })


def inject_a4_container_restart_loop(gcp, terminal, t0):
    """
    A4: Container Restart Loop (Terminal Handler, 09:30-09:34)
    Sources: GCP Cloud Metrics, Terminal Handler App Log
    """
    # Restarts in GCP
    gcp.append({
        "timestamp": ts(t0 + timedelta(minutes=2)),
        "project_id": "custom-sim",
        "resource_type": "gke_container",
        "resource_id": f"container-A4",
        "zone": "europe-west1-b",
        "metric_name": "container/restart_count",
        "metric_value": 1,
        "restart_count": 1,
        "pod_name": POD_NAME,
        "_anomaly": "A4_RESTART"
    })
    gcp.append({
        "timestamp": ts(t0 + timedelta(minutes=4)),
        "project_id": "custom-sim",
        "resource_type": "gke_container",
        "resource_id": f"container-A4",
        "zone": "europe-west1-b",
        "metric_name": "container/restart_count",
        "metric_value": 2,
        "restart_count": 2,
        "pod_name": POD_NAME,
        "_anomaly": "A4_RESTART"
    })
    
    # Startup loop in Terminal Handler
    for m, cid in [(0, "c1"), (2, "c2"), (4, "c3")]:
        terminal.append({
            "timestamp": ts(t0 + timedelta(minutes=m)),
            "event_type": "STARTUP",
            "container_id": f"container-{cid}",
            "pod_name": POD_NAME,
            "_anomaly": "A4_STARTUP",
        })
    # OOMs causing restarts
    for m in [0, 2]:
        terminal.append({
            "timestamp": ts(t0 + timedelta(minutes=m)),
            "log_level": "FATAL",
            "exception_class": "OutOfMemoryError",
            "pod_name": POD_NAME,
            "_anomaly": "A4_OOM",
        })


def inject_a5_response_time_spike(kafka, atm_app, t0):
    """
    A5: High Response Time Spike + Success Rate Drop (ATM-GB-0001, 09:30)
    Sources: Kafka Stream, ATM App Log
    """
    corr = SCENARIO_CORR["A5"]
    atm = "ATM-GB-0001"
    
    # Kafka spike
    vals = [(3200, 72.0, 8), (30000, 50.0, 14)]
    for i, (rt, sr, fc) in enumerate(vals):
        kafka.append({
            "timestamp": ts(t0 + timedelta(minutes=i)),
            "atm_id": atm,
            "response_time_ms": rt,
            "transaction_success_rate": sr,
            "failure_count": fc,
            "transaction_failure_reason": "TIMEOUT",
            "correlation_id": corr,
            "_anomaly": "A5_SPIKE",
        })
    
    # ATM App TIMEOUT
    atm_app.append({
        "timestamp": ts(t0),
        "atm_id": atm,
        "event_type": "TIMEOUT",
        "error_code": "ERR-0012",
        "response_time_ms": 3200,
        "correlation_id": corr,
        "_anomaly": "A5_APP_TIMEOUT",
    })


def inject_a6_os_memory_pressure(windows, atm_app, t0):
    """
    A6: OS Memory Pressure -> Application Timeout (ATM-GB-0002, 09:45)
    Sources: Windows OS Metrics, ATM App Log
    """
    atm = "ATM-GB-0002"
    # Windows ramp up (2 hours)
    for i in range(13):
        t = t0 + timedelta(minutes=i*10)
        windows.append({
            "timestamp": ts(t),
            "atm_id": atm,
            "memory_usage_percent": round(46.0 + (52.75 * i / 12), 2),
            "network_errors": i * 2,
            "cpu_usage_percent": round(30.0 + (61.5 * i / 12), 2),
            "_anomaly": "A6_RAMP",
        })
    
    # ATM App TIMEOUT correlated with OS pressure
    atm_app.append({
        "timestamp": ts(t0 + timedelta(minutes=120)),
        "atm_id": atm,
        "event_type": "TIMEOUT",
        "error_detail": "ThreadAbortException: memory pressure",
        "error_code": "ERR-MEM",
        "_anomaly": "A6_TIMEOUT",
    })


def inject_a7_malformed_kafka(kafka, prometheus):
    """
    A7: Malformed / Out-of-Order Kafka Events (ATM-GB-0004)
    Sources: Kafka Stream, Prometheus Metrics

    This anomaly SHOULD be sent straight to the ingestion_errors table.
    As to not crash the database intialisation process.
    """
    atm = "ATM-GB-0004"
    # Out of order
    kafka.append({
        "timestamp": ts(BASE_DATE + timedelta(hours=1)),
        "atm_id": atm,
        "kafka_offset": 4050,
        "_anomaly": "A7_OUT_OF_ORDER",
    })
    # Null fields
    kafka.append({
        "timestamp": ts(BASE_DATE + timedelta(hours=2)),
        "atm_id": atm,
        "atm_status": None,
        "transaction_rate_tps": None,
        "kafka_offset": 4051,
        "_anomaly": "A7_NULLS",
    })

    # Prometheus malformation per guide (09:33:00)
    # Note: Using BASE_DATE + 1h33m to simulate 09:33 (if BASE_DATE is 08:00)
    prometheus.append({
        "timestamp": ts(BASE_DATE + timedelta(hours=1, minutes=33)),
        "metric_name": "jvm_memory_used_bytes",
        "metric_value": "NO_NUMERIC_DATA", # fails regex rescue
        "pod_name": POD_NAME,
        "_anomaly": "A7_MALFORMED_PROM"
    })



def generate_dataset(output: str = OUTPUT_DIR, hours: int = HOURS, seed: int = SEED) -> None:
    random.seed(seed)
    ensure_output(output)
    start = BASE_DATE
    end = start + timedelta(hours=hours)

    print("Generating base metrics and logs...")
    atm_app = build_atm_app_log(start, end)
    hardware = build_hardware_log(start, end)
    terminal = build_terminal_handler_log(start, end)
    kafka = build_kafka_stream(start, end)
    prometheus = build_prometheus_metrics(start, end)
    windows = build_windows_os_metrics(start, end)
    gcp = build_gcp_metrics(start, end)

    print("Injecting correlated anomaly scenarios A1-A7...")
    inject_a1_network_timeout_cascade(atm_app, kafka, terminal, start + timedelta(hours=10))
    inject_a2_cassette_depletion(hardware, kafka, start + timedelta(hours=9))
    inject_a3_jvm_memory_leak(prometheus, gcp, terminal, start + timedelta(hours=8))
    inject_a4_container_restart_loop(gcp, terminal, start + timedelta(hours=9, minutes=30))
    inject_a5_response_time_spike(kafka, atm_app, start + timedelta(hours=9, minutes=30))
    inject_a6_os_memory_pressure(windows, atm_app, start + timedelta(hours=7, minutes=45))
    inject_a7_malformed_kafka(kafka, prometheus)

    print("Sorting and writing datasets...")
    for data in [atm_app, hardware, terminal, kafka, prometheus, windows, gcp]:
        data.sort(key=lambda r: r["timestamp"])

    write_json(atm_app, "atm_application_log.json", output)
    write_json(hardware, "atm_hardware_sensor_log.json", output)
    write_json(terminal, "terminal_handler_app_log.json", output)
    write_json(kafka, "kafka_atm_metrics_stream.json", output)

    write_csv(prometheus, PROMETHEUS_HEADERS + ["_anomaly"], "prometheus_metrics.csv", output)
    write_csv(windows, WINDOWS_HEADERS + ["_anomaly"], "windows_os_metrics.csv", output)
    write_csv(gcp, GCP_HEADERS + ["_anomaly"], "gcp_cloud_metrics.csv", output)


if __name__ == "__main__":
    generate_dataset()
    