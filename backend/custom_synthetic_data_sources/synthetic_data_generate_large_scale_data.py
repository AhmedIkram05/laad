"""
Large-Scale Synthetic Data Generator
=====================================
Log Aggregation, Analysis & Diagnostics Platform
NCR Atleos — 3rd Year CS Project

Generates 24 hours of synthetic operational data across 7 sources:
  1. ATM Application Log          (JSON)
  2. ATM Hardware Sensor Log      (JSON)
  3. Terminal Handler App Log     (JSON)
  4. Kafka ATM Metrics Stream     (JSON)
  5. Prometheus Metrics           (CSV)
  6. Windows OS Metrics           (CSV)
  7. GCP Cloud Metrics            (CSV)

Anomalies injected (all others are clean/error-free):
  A1 - Network timeout cascade              (ATM-GB-0003, ~10:00)
  A2 - Cash cassette depletion OOS          (ATM-GB-0003, 09:00–09:59)
  A3 - JVM memory leak → OOM               (Terminal Handler, 08:00–09:30)
  A4 - Container restart loop              (Terminal Handler, 09:30–09:34)
  A5 - High response time + success drop   (ATM-GB-0001, 09:30–09:31)
  A6 - OS memory pressure → app timeout    (ATM-GB-0002, 08:45–10:00)
  A7 - Malformed / out-of-order Kafka msg  (ATM-GB-0004, 08:14–08:15)

Usage:
  pip install faker
  python generate_large_scale_data.py

Output: ./output/ directory containing all 7 files.
"""

import json
import csv
import os
import random
import math
from datetime import datetime, timedelta, timezone
from uuid import uuid4

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

OUTPUT_DIR = "output"
SEED = 42
random.seed(SEED)

BASE_DATE = datetime(2026, 3, 5, 0, 0, 0, tzinfo=timezone.utc)
END_DATE   = datetime(2026, 3, 6, 0, 0, 0, tzinfo=timezone.utc)

ATMS = [
    {"id": "ATM-GB-0001", "location": "LOC-0101", "host": "ATM-HOST-0001"},
    {"id": "ATM-GB-0002", "location": "LOC-0202", "host": "ATM-HOST-0002"},
    {"id": "ATM-GB-0003", "location": "LOC-0303", "host": "ATM-HOST-0003"},
    {"id": "ATM-GB-0004", "location": "LOC-0404", "host": "ATM-HOST-0004"},
    {"id": "ATM-GB-0005", "location": "LOC-0505", "host": "ATM-HOST-0005"},
    {"id": "ATM-GB-0006", "location": "LOC-0606", "host": "ATM-HOST-0006"},
]

APP_VERSION    = "3.4.1-build.209"
OS_VERSION     = "Windows 10 LTSB 2016 Build 14393"
SVC_VERSION    = "2.7.0-SNAPSHOT"
SVC_NAME       = "terminal-handler"
GCP_PROJECT    = "synth-banking-sim-001"
GCP_ZONE       = "europe-west2-b"
SQL_INSTANCE   = "synth-sql-instance-01"

# Anomaly time windows (UTC)
A1_TIME  = datetime(2026, 3, 5, 10,  0, 0,  tzinfo=timezone.utc)
A2_START = datetime(2026, 3, 5,  9,  0, 0,  tzinfo=timezone.utc)
A2_END   = datetime(2026, 3, 5,  9, 59, 0,  tzinfo=timezone.utc)
A3_START = datetime(2026, 3, 5,  8,  0, 0,  tzinfo=timezone.utc)
A3_END   = datetime(2026, 3, 5,  9, 30, 0,  tzinfo=timezone.utc)
A4_START = datetime(2026, 3, 5,  9, 30, 0,  tzinfo=timezone.utc)
A4_END   = datetime(2026, 3, 5,  9, 34, 0,  tzinfo=timezone.utc)
A5_START = datetime(2026, 3, 5,  9, 30, 0,  tzinfo=timezone.utc)
A5_END   = datetime(2026, 3, 5,  9, 32, 0,  tzinfo=timezone.utc)
A6_START = datetime(2026, 3, 5,  8, 45, 0,  tzinfo=timezone.utc)
A6_END   = datetime(2026, 3, 5, 10,  0, 0,  tzinfo=timezone.utc)
A7_TIME  = datetime(2026, 3, 5,  8, 14, 0,  tzinfo=timezone.utc)

# Pod / container sequence for restart loop (A3/A4)
POD_NAME       = "terminal-handler-pod-7d9f-xk2lp"
CONTAINERS     = ["a3f2b19c04d1", "b7e91d33ff02", "c9d04e55aa11"]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def ts(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")

def jitter(base: float, pct: float = 0.10) -> float:
    """Return base ± pct random jitter, always positive."""
    return max(0.0, base * (1 + random.uniform(-pct, pct)))

def make_corr() -> str:
    return f"corr-{str(uuid4())[:18]}"

def make_txn() -> str:
    return f"txn-{str(uuid4())[:18]}"

def make_sess() -> str:
    return f"sess-{str(uuid4())[:12]}"

def container_at(dt: datetime) -> str:
    """Return which container ID was running at time dt (accounts for restarts)."""
    if dt >= A4_START + timedelta(seconds=55):
        return CONTAINERS[2]
    if dt >= A4_START + timedelta(seconds=15):
        return CONTAINERS[1]
    return CONTAINERS[0]

def minutes_range(start: datetime, end: datetime, step_minutes: int = 1):
    current = start
    while current < end:
        yield current
        current += timedelta(minutes=step_minutes)

def ensure_output():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
# Source 1: ATM Application Log
# ---------------------------------------------------------------------------

def build_atm_app_log() -> list:
    records = []

    for atm in ATMS:
        atm_id   = atm["id"]
        location = atm["location"]

        # ---- Startup at 00:00 ----
        records.append({
            "timestamp":       ts(BASE_DATE),
            "log_level":       "INFO",
            "atm_id":          atm_id,
            "location_code":   location,
            "session_id":      None,
            "correlation_id":  None,
            "transaction_id":  None,
            "event_type":      "STARTUP",
            "message":         "ATM client application started successfully. Self-test passed.",
            "component":       "BootManager",
            "thread_id":       1,
            "response_time_ms": None,
            "error_code":      None,
            "error_detail":    None,
            "atm_status":      "Online",
            "os_version":      OS_VERSION,
            "app_version":     APP_VERSION,
            "_anomaly":        None,
        })

        # ---- Normal transaction loop (every ~3–6 minutes) ----
        t = BASE_DATE + timedelta(minutes=2)
        tx_count = 0
        while t < END_DATE - timedelta(minutes=1):

            # Skip anomaly windows for the affected ATMs
            skip = False
            if atm_id == "ATM-GB-0003" and A1_TIME <= t < A1_TIME + timedelta(minutes=2):
                skip = True
            if atm_id == "ATM-GB-0003" and A2_START <= t < A2_END:
                skip = True  # cassettes draining — handled separately below

            interval_mins = random.uniform(3, 6)
            t_start = t

            if not skip:
                corr = make_corr()
                txn  = make_txn()
                sess = make_sess()
                tx_type = random.choice(["Withdrawal", "Balance Enquiry", "Mini Statement", "Deposit"])
                resp_ms = int(jitter(310, 0.15))

                records.append({
                    "timestamp":       ts(t_start),
                    "log_level":       "INFO",
                    "atm_id":          atm_id,
                    "location_code":   location,
                    "session_id":      sess,
                    "correlation_id":  corr,
                    "transaction_id":  txn,
                    "event_type":      "TRANSACTION_START",
                    "message":         f"{tx_type} transaction initiated.",
                    "component":       "TransactionManager",
                    "thread_id":       random.randint(2, 8),
                    "response_time_ms": None,
                    "error_code":      None,
                    "error_detail":    None,
                    "atm_status":      "Online",
                    "os_version":      OS_VERSION,
                    "app_version":     APP_VERSION,
                    "_anomaly":        None,
                })

                t_end = t_start + timedelta(milliseconds=resp_ms + random.randint(100, 400))
                amount = round(random.choice([20, 40, 50, 60, 80, 100, 150, 200, 250, 300]), 2)
                end_msg = (
                    f"{tx_type} completed successfully. Amount dispensed: {amount:.2f}"
                    if tx_type == "Withdrawal"
                    else f"{tx_type} completed successfully."
                )

                records.append({
                    "timestamp":       ts(t_end),
                    "log_level":       "INFO",
                    "atm_id":          atm_id,
                    "location_code":   location,
                    "session_id":      sess,
                    "correlation_id":  corr,
                    "transaction_id":  txn,
                    "event_type":      "TRANSACTION_END",
                    "message":         end_msg,
                    "component":       "TransactionManager",
                    "thread_id":       random.randint(2, 8),
                    "response_time_ms": resp_ms,
                    "error_code":      None,
                    "error_detail":    None,
                    "atm_status":      "Online",
                    "os_version":      OS_VERSION,
                    "app_version":     APP_VERSION,
                    "_anomaly":        None,
                })
                tx_count += 1

            t += timedelta(minutes=interval_mins)

        # ---- Hourly journal writes (normal) ----
        for h in range(1, 24):
            jt = BASE_DATE + timedelta(hours=h)
            records.append({
                "timestamp":       ts(jt),
                "log_level":       "INFO",
                "atm_id":          atm_id,
                "location_code":   location,
                "session_id":      None,
                "correlation_id":  None,
                "transaction_id":  None,
                "event_type":      "JOURNAL_WRITE",
                "message":         f"Hourly journal written. Transactions this hour: {random.randint(8, 20)}.",
                "component":       "JournalManager",
                "thread_id":       1,
                "response_time_ms": None,
                "error_code":      None,
                "error_detail":    None,
                "atm_status":      "Online",
                "os_version":      OS_VERSION,
                "app_version":     APP_VERSION,
                "_anomaly":        None,
            })

        # ---- Shutdown at 23:59 ----
        records.append({
            "timestamp":       ts(END_DATE - timedelta(seconds=1)),
            "log_level":       "INFO",
            "atm_id":          atm_id,
            "location_code":   location,
            "session_id":      None,
            "correlation_id":  None,
            "transaction_id":  None,
            "event_type":      "SHUTDOWN",
            "message":         "ATM client application performing graceful shutdown.",
            "component":       "BootManager",
            "thread_id":       1,
            "response_time_ms": None,
            "error_code":      None,
            "error_detail":    None,
            "atm_status":      "Online",
            "os_version":      OS_VERSION,
            "app_version":     APP_VERSION,
            "_anomaly":        None,
        })

    # ==== ANOMALY A5: ATM-GB-0001 high response time + timeout (09:30) ====
    corr_a5a = "corr-0010-xxyy-aabb-1234"
    corr_a5b = "corr-0011-xyzw-ccdd-5678"
    records += [
        {
            "timestamp": ts(A5_START + timedelta(seconds=1)),
            "log_level": "WARN",
            "atm_id": "ATM-GB-0001", "location_code": "LOC-0101",
            "session_id": "sess-0010-xxyy", "correlation_id": corr_a5a,
            "transaction_id": "txn-0010-aaaa-bbbb",
            "event_type": "TRANSACTION_START",
            "message": "Withdrawal transaction initiated. Host response slower than expected.",
            "component": "TransactionManager", "thread_id": 5,
            "response_time_ms": None, "error_code": None, "error_detail": None,
            "atm_status": "Online", "os_version": OS_VERSION, "app_version": APP_VERSION,
            "_anomaly": "A5",
        },
        {
            "timestamp": ts(A5_START + timedelta(seconds=4, milliseconds=200)),
            "log_level": "WARN",
            "atm_id": "ATM-GB-0001", "location_code": "LOC-0101",
            "session_id": "sess-0010-xxyy", "correlation_id": corr_a5a,
            "transaction_id": "txn-0010-aaaa-bbbb",
            "event_type": "TRANSACTION_END",
            "message": "Transaction completed but response time exceeded threshold. Amount dispensed: 200.00",
            "component": "TransactionManager", "thread_id": 5,
            "response_time_ms": 3200, "error_code": None, "error_detail": None,
            "atm_status": "Online", "os_version": OS_VERSION, "app_version": APP_VERSION,
            "_anomaly": "A5",
        },
        {
            "timestamp": ts(A5_START + timedelta(minutes=1, seconds=10)),
            "log_level": "ERROR",
            "atm_id": "ATM-GB-0001", "location_code": "LOC-0101",
            "session_id": "sess-0011-xyzw", "correlation_id": corr_a5b,
            "transaction_id": "txn-0011-cccc-dddd",
            "event_type": "TIMEOUT",
            "message": "Transaction timed out waiting for host authorisation response.",
            "component": "NetworkClient", "thread_id": 5,
            "response_time_ms": 30000,
            "error_code": "ERR-0012",
            "error_detail": "SocketTimeoutException: Read timed out after 30000ms waiting for host response.",
            "atm_status": "Online", "os_version": OS_VERSION, "app_version": APP_VERSION,
            "_anomaly": "A5",
        },
    ]

    # ==== ANOMALY A6: ATM-GB-0002 OS memory pressure → timeout (09:45) ====
    records += [
        {
            "timestamp": ts(A6_END - timedelta(minutes=15, seconds=0)),
            "log_level": "WARN",
            "atm_id": "ATM-GB-0002", "location_code": "LOC-0202",
            "session_id": "sess-0020-mmnn", "correlation_id": "corr-0020-mmnn-eeff-9012",
            "transaction_id": "txn-0020-eeee-ffff",
            "event_type": "TRANSACTION_START",
            "message": "Withdrawal transaction initiated. System resources under pressure.",
            "component": "TransactionManager", "thread_id": 3,
            "response_time_ms": None, "error_code": None, "error_detail": None,
            "atm_status": "Online", "os_version": OS_VERSION, "app_version": APP_VERSION,
            "_anomaly": "A6",
        },
        {
            "timestamp": ts(A6_END - timedelta(minutes=15) + timedelta(seconds=31, milliseconds=500)),
            "log_level": "ERROR",
            "atm_id": "ATM-GB-0002", "location_code": "LOC-0202",
            "session_id": "sess-0020-mmnn", "correlation_id": "corr-0020-mmnn-eeff-9012",
            "transaction_id": "txn-0020-eeee-ffff",
            "event_type": "TIMEOUT",
            "message": "Transaction processing stalled. Suspected OS memory paging. Operation aborted.",
            "component": "TransactionManager", "thread_id": 3,
            "response_time_ms": 31500,
            "error_code": "ERR-0031",
            "error_detail": "System.Threading.ThreadAbortException: Thread was being aborted. Possible memory pressure causing paging delay.",
            "atm_status": "Online", "os_version": OS_VERSION, "app_version": APP_VERSION,
            "_anomaly": "A6",
        },
    ]

    # ==== ANOMALY A1: ATM-GB-0003 network disconnect (10:00) ====
    records += [
        {
            "timestamp": ts(A1_TIME),
            "log_level": "ERROR",
            "atm_id": "ATM-GB-0003", "location_code": "LOC-0303",
            "session_id": None, "correlation_id": "corr-0030-nnet-disc-0001",
            "transaction_id": None,
            "event_type": "NETWORK_DISCONNECT",
            "message": "Network connection to Terminal Handler lost. Attempting reconnection.",
            "component": "NetworkClient", "thread_id": 2,
            "response_time_ms": None,
            "error_code": "ERR-0040",
            "error_detail": "IOException: Connection reset by peer. Remote endpoint: 10.0.0.50:8443",
            "atm_status": "Offline", "os_version": OS_VERSION, "app_version": APP_VERSION,
            "_anomaly": "A1",
        },
        {
            "timestamp": ts(A1_TIME + timedelta(seconds=45)),
            "log_level": "ERROR",
            "atm_id": "ATM-GB-0003", "location_code": "LOC-0303",
            "session_id": "sess-0030-rrss", "correlation_id": "corr-0031-rrss-gggg-3456",
            "transaction_id": "txn-0030-gggg-hhhh",
            "event_type": "TIMEOUT",
            "message": "Transaction failed. No network connectivity to Terminal Handler.",
            "component": "NetworkClient", "thread_id": 6,
            "response_time_ms": 30000,
            "error_code": "ERR-0041",
            "error_detail": "SocketException: Network is unreachable.",
            "atm_status": "Offline", "os_version": OS_VERSION, "app_version": APP_VERSION,
            "_anomaly": "A1",
        },
        {
            "timestamp": ts(A1_TIME + timedelta(minutes=2, seconds=10)),
            "log_level": "INFO",
            "atm_id": "ATM-GB-0003", "location_code": "LOC-0303",
            "session_id": None, "correlation_id": "corr-0030-nnet-disc-0001",
            "transaction_id": None,
            "event_type": "NETWORK_CONNECT",
            "message": "Network connection to Terminal Handler re-established after 130 seconds.",
            "component": "NetworkClient", "thread_id": 2,
            "response_time_ms": None, "error_code": None, "error_detail": None,
            "atm_status": "Online", "os_version": OS_VERSION, "app_version": APP_VERSION,
            "_anomaly": "A1",
        },
    ]

    records.sort(key=lambda r: r["timestamp"])
    return records


# ---------------------------------------------------------------------------
# Source 2: ATM Hardware Sensor Log
# ---------------------------------------------------------------------------

def build_hardware_log() -> list:
    records = []

    for atm in ATMS:
        atm_id = atm["id"]

        # Startup self-tests
        for component, fw in [
            ("CASH_DISPENSER", "FW-2.1.4"),
            ("CARD_READER",    "FW-1.8.2"),
            ("RECEIPT_PRINTER","FW-1.3.0"),
            ("KEYPAD",         "FW-1.1.0"),
            ("TEMPERATURE_SENSOR","FW-1.0.1"),
            ("UPS",            "FW-3.2.0"),
        ]:
            records.append({
                "timestamp":    ts(BASE_DATE + timedelta(seconds=random.randint(2, 15))),
                "atm_id":       atm_id,
                "correlation_id": None,
                "component":    component,
                "event_type":   "SELF_TEST_PASS",
                "severity":     "INFO",
                "message":      f"{component.replace('_',' ').title()} self-test passed.",
                "metric_name":  None,
                "metric_value": None,
                "metric_unit":  None,
                "threshold_value": None,
                "firmware_version": fw,
                "_anomaly":     None,
            })

        # Periodic temperature readings every 30 mins
        for t in minutes_range(BASE_DATE, END_DATE, step_minutes=30):
            temp = round(jitter(35.0, 0.08), 1)
            records.append({
                "timestamp":    ts(t),
                "atm_id":       atm_id,
                "correlation_id": None,
                "component":    "TEMPERATURE_SENSOR",
                "event_type":   "TEMPERATURE_NORMAL",
                "severity":     "INFO",
                "message":      f"Internal temperature within normal range: {temp}°C.",
                "metric_name":  "internal_temp_celsius",
                "metric_value": temp,
                "metric_unit":  "celsius",
                "threshold_value": 55.0,
                "firmware_version": "FW-1.0.1",
                "_anomaly":     None,
            })

        # Periodic UPS status every 60 mins
        for t in minutes_range(BASE_DATE, END_DATE, step_minutes=60):
            records.append({
                "timestamp":    ts(t),
                "atm_id":       atm_id,
                "correlation_id": None,
                "component":    "UPS",
                "event_type":   "STATUS_OK",
                "severity":     "INFO",
                "message":      "UPS on mains power. Battery charge: 100%.",
                "metric_name":  "ups_battery_charge_percent",
                "metric_value": 100.0,
                "metric_unit":  "percent",
                "threshold_value": 20.0,
                "firmware_version": "FW-3.2.0",
                "_anomaly":     None,
            })

        # Cash dispenser checks every 60 mins (normal — high note counts for non-anomaly ATMs)
        if atm_id != "ATM-GB-0003":
            for i, t in enumerate(minutes_range(BASE_DATE, END_DATE, step_minutes=60)):
                notes = max(200, 1000 - i * random.randint(5, 15))
                records.append({
                    "timestamp":    ts(t),
                    "atm_id":       atm_id,
                    "correlation_id": None,
                    "component":    "CASH_DISPENSER",
                    "event_type":   "STATUS_OK",
                    "severity":     "INFO",
                    "message":      f"Cash dispenser status OK. Total notes: {notes}.",
                    "metric_name":  "cassette_note_count",
                    "metric_value": notes,
                    "metric_unit":  "notes",
                    "threshold_value": 50,
                    "firmware_version": "FW-2.1.4",
                    "_anomaly":     None,
                })

    # ==== ANOMALY A2: ATM-GB-0003 cassette depletion ====
    # Notes drain from 120 at 08:00 to empty by 09:59
    a2_notes_c1 = 80
    a2_notes_c2 = 65
    for i, t in enumerate(minutes_range(BASE_DATE + timedelta(hours=8), A2_END, step_minutes=15)):
        c1 = max(0, a2_notes_c1 - i * 18)
        c2 = max(0, a2_notes_c2 - i * 15)
        total = c1 + c2

        if total == 0:
            evt, sev = "CASSETTE_EMPTY", "CRITICAL"
            msg = "All cash cassettes empty. ATM transitioning to Out of Service."
        elif total < 50:
            evt, sev = "CASSETTE_LOW", "WARNING"
            msg = f"Cash cassette levels critically low. Remaining: {total} notes."
        elif total < 100:
            evt, sev = "CASSETTE_LOW", "WARNING"
            msg = f"Cash cassette level below warning threshold. Remaining: {total} notes."
        else:
            evt, sev = "STATUS_OK", "INFO"
            msg = f"Cash dispenser status OK. Total notes: {total}."

        records.append({
            "timestamp":    ts(t),
            "atm_id":       "ATM-GB-0003",
            "correlation_id": None,
            "component":    "CASH_DISPENSER",
            "event_type":   evt,
            "severity":     sev,
            "message":      msg,
            "metric_name":  "cassette_note_count",
            "metric_value": total,
            "metric_unit":  "notes",
            "threshold_value": 50,
            "firmware_version": "FW-2.1.4",
            "_anomaly":     "A2",
        })

    records.sort(key=lambda r: r["timestamp"])
    return records


# ---------------------------------------------------------------------------
# Source 3: Terminal Handler Application Log
# ---------------------------------------------------------------------------

def build_th_app_log() -> list:
    records = []

    # Startup
    records.append({
        "timestamp": ts(BASE_DATE - timedelta(minutes=5)),
        "log_level": "INFO",
        "service_name": SVC_NAME, "service_version": SVC_VERSION,
        "container_id": CONTAINERS[0], "pod_name": POD_NAME,
        "correlation_id": None, "transaction_id": None, "atm_id": None,
        "event_type": "STARTUP",
        "message": "Terminal Handler service started. Listening on port 8443. DB connected. Kafka ready.",
        "logger_name": "com.synthbank.terminalhandler.Application",
        "thread_name": "main",
        "response_time_ms": None, "http_status_code": None,
        "exception_class": None, "exception_message": None,
        "db_query_time_ms": None, "environment": "prod-sim",
        "_anomaly": None,
    })

    # Normal request/response pairs every ~2–4 minutes for each ATM
    for atm in ATMS:
        atm_id = atm["id"]
        t = BASE_DATE + timedelta(minutes=random.uniform(1, 3))
        while t < END_DATE - timedelta(minutes=1):
            # Skip anomaly windows
            if A4_START <= t < A4_END:
                t += timedelta(minutes=random.uniform(2, 4))
                continue

            corr = make_corr()
            txn  = make_txn()
            db_ms = int(jitter(18, 0.20))
            resp_ms = int(jitter(305, 0.12))

            records.append({
                "timestamp": ts(t),
                "log_level": "INFO",
                "service_name": SVC_NAME, "service_version": SVC_VERSION,
                "container_id": container_at(t), "pod_name": POD_NAME,
                "correlation_id": corr, "transaction_id": txn, "atm_id": atm_id,
                "event_type": "REQUEST_RECEIVED",
                "message": f"Transaction request received from {atm_id}.",
                "logger_name": "com.synthbank.terminalhandler.TransactionService",
                "thread_name": f"http-nio-8443-exec-{random.randint(1, 10)}",
                "response_time_ms": None, "http_status_code": None,
                "exception_class": None, "exception_message": None,
                "db_query_time_ms": None, "environment": "prod-sim",
                "_anomaly": None,
            })

            records.append({
                "timestamp": ts(t + timedelta(milliseconds=db_ms)),
                "log_level": "INFO",
                "service_name": SVC_NAME, "service_version": SVC_VERSION,
                "container_id": container_at(t), "pod_name": POD_NAME,
                "correlation_id": corr, "transaction_id": txn, "atm_id": atm_id,
                "event_type": "DB_QUERY",
                "message": "Account authorisation query executed.",
                "logger_name": "com.synthbank.terminalhandler.repository.AccountRepository",
                "thread_name": f"http-nio-8443-exec-{random.randint(1, 10)}",
                "response_time_ms": None, "http_status_code": None,
                "exception_class": None, "exception_message": None,
                "db_query_time_ms": db_ms, "environment": "prod-sim",
                "_anomaly": None,
            })

            records.append({
                "timestamp": ts(t + timedelta(milliseconds=resp_ms)),
                "log_level": "INFO",
                "service_name": SVC_NAME, "service_version": SVC_VERSION,
                "container_id": container_at(t), "pod_name": POD_NAME,
                "correlation_id": corr, "transaction_id": txn, "atm_id": atm_id,
                "event_type": "RESPONSE_SENT",
                "message": f"Authorisation approved. Response sent to {atm_id}.",
                "logger_name": "com.synthbank.terminalhandler.TransactionService",
                "thread_name": f"http-nio-8443-exec-{random.randint(1, 10)}",
                "response_time_ms": resp_ms, "http_status_code": 200,
                "exception_class": None, "exception_message": None,
                "db_query_time_ms": None, "environment": "prod-sim",
                "_anomaly": None,
            })

            t += timedelta(minutes=random.uniform(2, 4))

    # Hourly health checks
    for h in range(24):
        ht = BASE_DATE + timedelta(hours=h, minutes=30)
        records.append({
            "timestamp": ts(ht),
            "log_level": "INFO",
            "service_name": SVC_NAME, "service_version": SVC_VERSION,
            "container_id": container_at(ht), "pod_name": POD_NAME,
            "correlation_id": None, "transaction_id": None, "atm_id": None,
            "event_type": "HEALTH_CHECK",
            "message": f"Health check passed. DB: OK. Kafka: OK. ATMs connected: {len(ATMS)}/{len(ATMS)}.",
            "logger_name": "com.synthbank.terminalhandler.HealthEndpoint",
            "thread_name": "health-check-scheduler",
            "response_time_ms": random.randint(8, 18), "http_status_code": 200,
            "exception_class": None, "exception_message": None,
            "db_query_time_ms": None, "environment": "prod-sim",
            "_anomaly": None,
        })

    # ==== ANOMALY A3: Slow DB queries due to GC pressure ====
    records += [
        {
            "timestamp": ts(BASE_DATE + timedelta(hours=9, seconds=1)),
            "log_level": "WARN",
            "service_name": SVC_NAME, "service_version": SVC_VERSION,
            "container_id": CONTAINERS[0], "pod_name": POD_NAME,
            "correlation_id": "corr-0005-slow-db-0001", "transaction_id": "txn-0005-slow-0001",
            "atm_id": "ATM-GB-0002",
            "event_type": "DB_QUERY",
            "message": "Account authorisation query slow. Possible GC pause interference.",
            "logger_name": "com.synthbank.terminalhandler.repository.AccountRepository",
            "thread_name": "http-nio-8443-exec-3",
            "response_time_ms": None, "http_status_code": None,
            "exception_class": None, "exception_message": None,
            "db_query_time_ms": 520, "environment": "prod-sim",
            "_anomaly": "A3",
        },
        {
            "timestamp": ts(BASE_DATE + timedelta(hours=9, minutes=15, seconds=10)),
            "log_level": "WARN",
            "service_name": SVC_NAME, "service_version": SVC_VERSION,
            "container_id": CONTAINERS[0], "pod_name": POD_NAME,
            "correlation_id": "corr-0006-slow-db-0002", "transaction_id": "txn-0006-slow-0002",
            "atm_id": "ATM-GB-0001",
            "event_type": "DB_QUERY",
            "message": "Account authorisation query very slow. JVM heap near capacity.",
            "logger_name": "com.synthbank.terminalhandler.repository.AccountRepository",
            "thread_name": "http-nio-8443-exec-5",
            "response_time_ms": None, "http_status_code": None,
            "exception_class": None, "exception_message": None,
            "db_query_time_ms": 1840, "environment": "prod-sim",
            "_anomaly": "A3",
        },
    ]

    # ==== ANOMALY A4: Container restart loop (OOM x2, 3 startups) ====
    records += [
        {
            "timestamp": ts(A4_START),
            "log_level": "FATAL",
            "service_name": SVC_NAME, "service_version": SVC_VERSION,
            "container_id": CONTAINERS[0], "pod_name": POD_NAME,
            "correlation_id": None, "transaction_id": None, "atm_id": None,
            "event_type": "EXCEPTION",
            "message": "Unhandled OutOfMemoryError. JVM terminating.",
            "logger_name": "com.synthbank.terminalhandler.Application",
            "thread_name": "http-nio-8443-exec-7",
            "response_time_ms": None, "http_status_code": None,
            "exception_class": "java.lang.OutOfMemoryError",
            "exception_message": "Java heap space. Requested array size exceeds VM limit.",
            "db_query_time_ms": None, "environment": "prod-sim",
            "_anomaly": "A4",
        },
        {
            "timestamp": ts(A4_START + timedelta(seconds=15)),
            "log_level": "INFO",
            "service_name": SVC_NAME, "service_version": SVC_VERSION,
            "container_id": CONTAINERS[1], "pod_name": POD_NAME,
            "correlation_id": None, "transaction_id": None, "atm_id": None,
            "event_type": "STARTUP",
            "message": "Terminal Handler service restarted (restart count: 1). Reconnecting.",
            "logger_name": "com.synthbank.terminalhandler.Application",
            "thread_name": "main",
            "response_time_ms": None, "http_status_code": None,
            "exception_class": None, "exception_message": None,
            "db_query_time_ms": None, "environment": "prod-sim",
            "_anomaly": "A4",
        },
        {
            "timestamp": ts(A4_START + timedelta(minutes=3, seconds=40)),
            "log_level": "FATAL",
            "service_name": SVC_NAME, "service_version": SVC_VERSION,
            "container_id": CONTAINERS[1], "pod_name": POD_NAME,
            "correlation_id": None, "transaction_id": None, "atm_id": None,
            "event_type": "EXCEPTION",
            "message": "Unhandled OutOfMemoryError. JVM terminating again.",
            "logger_name": "com.synthbank.terminalhandler.Application",
            "thread_name": "http-nio-8443-exec-2",
            "response_time_ms": None, "http_status_code": None,
            "exception_class": "java.lang.OutOfMemoryError",
            "exception_message": "Java heap space.",
            "db_query_time_ms": None, "environment": "prod-sim",
            "_anomaly": "A4",
        },
        {
            "timestamp": ts(A4_START + timedelta(minutes=3, seconds=55)),
            "log_level": "INFO",
            "service_name": SVC_NAME, "service_version": SVC_VERSION,
            "container_id": CONTAINERS[2], "pod_name": POD_NAME,
            "correlation_id": None, "transaction_id": None, "atm_id": None,
            "event_type": "STARTUP",
            "message": "Terminal Handler service restarted (restart count: 2). Reconnecting.",
            "logger_name": "com.synthbank.terminalhandler.Application",
            "thread_name": "main",
            "response_time_ms": None, "http_status_code": None,
            "exception_class": None, "exception_message": None,
            "db_query_time_ms": None, "environment": "prod-sim",
            "_anomaly": "A4",
        },
    ]

    # ==== ANOMALY A1: Terminal Handler marks ATM-GB-0003 offline ====
    records.append({
        "timestamp": ts(A1_TIME + timedelta(seconds=1)),
        "log_level": "ERROR",
        "service_name": SVC_NAME, "service_version": SVC_VERSION,
        "container_id": CONTAINERS[2], "pod_name": POD_NAME,
        "correlation_id": "corr-0030-nnet-disc-0001",
        "transaction_id": None, "atm_id": "ATM-GB-0003",
        "event_type": "NETWORK_TIMEOUT",
        "message": "ATM-GB-0003 connection dropped. No heartbeat for 60 seconds. Marking ATM as Offline.",
        "logger_name": "com.synthbank.terminalhandler.AtmConnectionManager",
        "thread_name": "heartbeat-monitor-1",
        "response_time_ms": None, "http_status_code": None,
        "exception_class": None, "exception_message": None,
        "db_query_time_ms": None, "environment": "prod-sim",
        "_anomaly": "A1",
    })

    records.sort(key=lambda r: r["timestamp"])
    return records


# ---------------------------------------------------------------------------
# Source 4: Kafka ATM Metrics Stream
# ---------------------------------------------------------------------------

def build_kafka_stream() -> list:
    records = []
    offsets = {atm["id"]: 1000 + i * 1000 for i, atm in enumerate(ATMS)}

    a3_oom_time = A4_START  # OOM at 09:30

    for t in minutes_range(BASE_DATE, END_DATE, step_minutes=1):
        for atm in ATMS:
            atm_id  = atm["id"]
            offsets[atm_id] += 1
            offset  = offsets[atm_id]
            corr    = None
            anomaly = None

            # Defaults — normal clean operation
            status         = "Online"
            tps            = round(jitter(1.2, 0.20), 2)
            resp_ms        = int(jitter(300, 0.12))
            success_rate   = round(random.uniform(99.0, 100.0), 2)
            failure_reason = "NONE"
            fail_count     = 0
            vol_increment  = random.randint(1, 3)

            # ---- ANOMALY A5: ATM-GB-0001 at 09:30–09:31 ----
            if atm_id == "ATM-GB-0001" and A5_START <= t < A5_END:
                anomaly        = "A5"
                tps            = round(jitter(0.2, 0.10), 2)
                resp_ms        = 30000 if t >= A5_START + timedelta(minutes=1) else 3200
                success_rate   = 50.0  if t >= A5_START + timedelta(minutes=1) else 72.0
                failure_reason = "NETWORK_TIMEOUT"
                fail_count     = 14   if t >= A5_START + timedelta(minutes=1) else 8
                corr           = "corr-0010-xxyy-aabb-1234"

            # ---- ANOMALY A2: ATM-GB-0003 cassette drain ----
            elif atm_id == "ATM-GB-0003" and A2_START <= t < A2_END:
                anomaly = "A2"
                mins_in = (t - A2_START).seconds // 60
                fraction_depleted = mins_in / 59.0
                if fraction_depleted >= 0.98:
                    status         = "Out of Service"
                    tps            = 0.0
                    resp_ms        = 0
                    success_rate   = 0.0
                    failure_reason = "CASH_DISPENSE_ERROR"
                    fail_count     = 3
                else:
                    success_rate   = round(100.0 - fraction_depleted * 40, 2)
                    failure_reason = "CASH_DISPENSE_ERROR" if fraction_depleted > 0.5 else "NONE"
                    fail_count     = int(fraction_depleted * 5)

            # ---- ANOMALY A1: ATM-GB-0003 offline ----
            elif atm_id == "ATM-GB-0003" and A1_TIME <= t < A1_TIME + timedelta(minutes=2):
                anomaly        = "A1"
                status         = "Offline"
                tps            = 0.0
                resp_ms        = 0
                success_rate   = 0.0
                failure_reason = "HOST_UNAVAILABLE"
                fail_count     = 0
                corr           = "corr-0030-nnet-disc-0001"

            # ---- ANOMALY A4: Terminal Handler down → ATMs queuing ----
            elif A4_START <= t < A4_END:
                anomaly        = "A4"
                tps            = 0.0
                resp_ms        = 0
                success_rate   = 0.0
                failure_reason = "HOST_UNAVAILABLE"
                fail_count     = 0

            # Compute running volume
            base_vol = int((t - BASE_DATE).total_seconds() / 60 * 1.2)
            vol = base_vol + random.randint(0, 5)

            rec = {
                "timestamp":               ts(t),
                "event_id":                f"evt-{atm_id[-4:]}-{offset:06d}",
                "correlation_id":          corr,
                "atm_id":                  atm_id,
                "atm_status":              status,
                "transaction_rate_tps":    tps,
                "response_time_ms":        resp_ms,
                "transaction_volume":      vol,
                "transaction_success_rate": success_rate,
                "transaction_failure_reason": failure_reason,
                "failure_count":           fail_count,
                "window_duration_seconds": 60,
                "kafka_partition":         ATMS.index(atm),
                "kafka_offset":            offset,
                "_anomaly":                anomaly,
            }
            records.append(rec)

    # ==== ANOMALY A7: Out-of-order + malformed events for ATM-GB-0004 ====
    oo_offset = offsets["ATM-GB-0004"] + 1
    records.append({
        "timestamp":               ts(A7_TIME),
        "event_id":                f"evt-0004-{oo_offset:06d}",
        "correlation_id":          None,
        "atm_id":                  "ATM-GB-0004",
        "atm_status":              "Online",
        "transaction_rate_tps":    1.1,
        "response_time_ms":        300,
        "transaction_volume":      50,
        "transaction_success_rate": 100.0,
        "transaction_failure_reason": "NONE",
        "failure_count":           0,
        "window_duration_seconds": 60,
        "kafka_partition":         ATMS.index(next(a for a in ATMS if a["id"] == "ATM-GB-0004")),
        "kafka_offset":            oo_offset,
        "_anomaly":                "A7_OUT_OF_ORDER",
    })
    records.append({
        "timestamp":               ts(A7_TIME + timedelta(minutes=1)),
        "event_id":                f"evt-0004-{oo_offset + 1:06d}",
        "correlation_id":          None,
        "atm_id":                  "ATM-GB-0004",
        "atm_status":              None,       # MISSING REQUIRED FIELD
        "transaction_rate_tps":    None,        # MISSING REQUIRED FIELD
        "response_time_ms":        310,
        "transaction_volume":      51,
        "transaction_success_rate": 100.0,
        "transaction_failure_reason": "NONE",
        "failure_count":           0,
        "window_duration_seconds": 60,
        "kafka_partition":         ATMS.index(next(a for a in ATMS if a["id"] == "ATM-GB-0004")),
        "kafka_offset":            oo_offset + 1,
        "_anomaly":                "A7_MALFORMED",
    })

    records.sort(key=lambda r: r["timestamp"])
    return records


# ---------------------------------------------------------------------------
# Source 5: Prometheus Metrics (CSV)
# ---------------------------------------------------------------------------

PROM_FIELDNAMES = [
    "timestamp", "metric_name", "metric_type", "metric_value",
    "service_name", "pod_name", "container_id",
    "label_area", "label_env", "help_text", "_anomaly",
]

JVM_MAX_BYTES = 1073741824  # 1 GB heap max

def build_prometheus_metrics() -> list:
    rows = []

    # Baseline heap at midnight
    baseline_heap = 314572800  # 300 MB

    for t in minutes_range(BASE_DATE, END_DATE, step_minutes=1):
        container = container_at(t)
        elapsed_secs = (t - BASE_DATE).total_seconds()

        # ---- Determine heap level ----
        anomaly_tag = None

        if t < A3_START:
            # Pre-anomaly: stable
            heap = int(jitter(baseline_heap, 0.03))

        elif A3_START <= t < A4_START:
            # ANOMALY A3: linear leak from 300 MB → 1040 MB over 90 mins
            anomaly_tag = "A3"
            progress = min(1.0, (t - A3_START).total_seconds() / (90 * 60))
            heap = int(baseline_heap + progress * (1040187392 - baseline_heap))
            heap = int(jitter(heap, 0.01))

        elif A4_START <= t < A4_START + timedelta(seconds=15):
            # Container crashed
            anomaly_tag = "A4"
            heap = 0

        elif A4_START + timedelta(seconds=15) <= t < A4_START + timedelta(minutes=3, seconds=40):
            # ANOMALY A4: restart 1 — heap climbs again fast
            anomaly_tag = "A4"
            progress = (t - (A4_START + timedelta(seconds=15))).total_seconds() / (3 * 60 + 25)
            heap = int(baseline_heap + progress * (1040187392 - baseline_heap))

        elif A4_START + timedelta(minutes=3, seconds=40) <= t < A4_START + timedelta(minutes=3, seconds=55):
            anomaly_tag = "A4"
            heap = 0

        elif A4_START + timedelta(minutes=3, seconds=55) <= t < A4_START + timedelta(minutes=30):
            # Restart 2 — heap resets, stable
            anomaly_tag = "A4"
            heap = int(jitter(baseline_heap, 0.03))

        else:
            # Post-anomaly: stable
            heap = int(jitter(baseline_heap + 50000000, 0.03))

        # GC pause sum grows with heap pressure
        if heap > 0:
            gc_pressure = max(0.0, (heap - 500000000) / (JVM_MAX_BYTES - 500000000))
            gc_sum = round(elapsed_secs * 0.0005 + gc_pressure * 25.0, 3)
        else:
            gc_sum = 0.0

        # CPU usage
        cpu = round(min(0.98, 0.08 + gc_pressure * 0.86), 4) if heap > 0 else 0.0

        if heap == 0:
            continue  # container restarting — no metrics emitted

        base_rows = [
            ("jvm_memory_used_bytes",   "gauge",   heap,        "heap",  "Used bytes of JVM heap memory"),
            ("jvm_memory_max_bytes",    "gauge",   JVM_MAX_BYTES, "heap","Max bytes of JVM heap memory"),
            ("process_cpu_usage",       "gauge",   cpu,          "",     "Process CPU usage fraction"),
            ("jvm_gc_pause_seconds_sum","counter", gc_sum,       "",     "Total time in GC pauses"),
            ("jvm_threads_live_threads","gauge",   random.randint(25, 35), "", "Live JVM threads"),
            ("db_connection_pool_active","gauge",  min(10, 2 + int(gc_pressure * 8)), "", "Active DB connections"),
            ("db_connection_pool_idle", "gauge",   max(0, 8 - int(gc_pressure * 8)),  "", "Idle DB connections"),
            ("terminal_handler_transactions_processed_total", "counter",
             int(elapsed_secs / 30), "", "Total transactions processed"),
            ("terminal_handler_transactions_failed_total", "counter",
             int(elapsed_secs / 30 * 0.01 + gc_pressure * 5), "", "Total failed transactions"),
        ]

        for metric_name, mtype, mval, area, help_txt in base_rows:
            rows.append({
                "timestamp":    ts(t),
                "metric_name":  metric_name,
                "metric_type":  mtype,
                "metric_value": mval,
                "service_name": SVC_NAME,
                "pod_name":     POD_NAME,
                "container_id": container,
                "label_area":   area,
                "label_env":    "prod-sim",
                "help_text":    help_txt,
                "_anomaly":     anomaly_tag,
            })

    # ==== ANOMALY A7: malformed Prometheus row ====
    rows.append({
        "timestamp":    ts(BASE_DATE + timedelta(hours=9, minutes=33)),
        "metric_name":  "jvm_memory_used_bytes",
        "metric_type":  "gauge",
        "metric_value": "890iembre",   # NON-NUMERIC — malformed
        "service_name": SVC_NAME,
        "pod_name":     POD_NAME,
        "container_id": CONTAINERS[1],
        "label_area":   "heap",
        "label_env":    "prod-sim",
        "help_text":    "Used bytes of JVM heap memory",
        "_anomaly":     "A7_MALFORMED",
    })

    rows.sort(key=lambda r: r["timestamp"])
    return rows


# ---------------------------------------------------------------------------
# Source 6: Windows OS Metrics (CSV)
# ---------------------------------------------------------------------------

WIN_FIELDNAMES = [
    "timestamp", "atm_id", "hostname", "os_version",
    "cpu_usage_percent", "memory_used_mb", "memory_total_mb", "memory_usage_percent",
    "disk_read_bytes_per_sec", "disk_write_bytes_per_sec", "disk_free_gb",
    "network_bytes_sent_per_sec", "network_bytes_recv_per_sec",
    "network_errors", "process_count", "system_uptime_seconds",
    "event_log_errors_last_min", "_anomaly",
]

def build_windows_os_metrics() -> list:
    rows = []
    total_mem = 4096.0
    base_uptime = {atm["id"]: random.randint(400000, 900000) for atm in ATMS}

    for t in minutes_range(BASE_DATE, END_DATE, step_minutes=1):
        elapsed = int((t - BASE_DATE).total_seconds())

        for atm in ATMS:
            atm_id   = atm["id"]
            hostname = atm["host"]
            anomaly  = None

            # Defaults — clean normal operation
            cpu     = round(jitter(12.0, 0.15), 1)
            mem_mb  = round(jitter(1850.0, 0.05), 1)
            disk_r  = int(jitter(200000, 0.10))
            disk_w  = int(jitter(50000, 0.10))
            disk_fr = round(jitter(18.5, 0.02), 1)
            net_s   = int(jitter(12000, 0.15))
            net_r   = int(jitter(8000, 0.15))
            net_err = 0
            procs   = random.randint(68, 76)
            ev_errs = 0

            # ==== ANOMALY A6: ATM-GB-0002 memory pressure ====
            if atm_id == "ATM-GB-0002" and A6_START <= t <= A6_END:
                anomaly = "A6"
                progress = (t - A6_START).total_seconds() / (A6_END - A6_START).total_seconds()
                mem_mb  = round(1900 + progress * (4044 - 1900), 1)
                cpu     = round(10.0 + progress * 81.5, 1)
                net_err = int(progress * 22)
                net_s   = max(256, int(12000 * (1 - progress * 0.95)))
                net_r   = max(128, int(8000  * (1 - progress * 0.95)))
                disk_w  = int(50000 + progress * 770000)
                procs   = random.randint(70, 70 + int(progress * 21))
                ev_errs = int(progress * 28)

            mem_pct = round((mem_mb / total_mem) * 100, 2)
            uptime  = base_uptime[atm_id] + elapsed

            rows.append({
                "timestamp":                ts(t),
                "atm_id":                   atm_id,
                "hostname":                 hostname,
                "os_version":               OS_VERSION,
                "cpu_usage_percent":        cpu,
                "memory_used_mb":           mem_mb,
                "memory_total_mb":          total_mem,
                "memory_usage_percent":     mem_pct,
                "disk_read_bytes_per_sec":  disk_r,
                "disk_write_bytes_per_sec": disk_w,
                "disk_free_gb":             disk_fr,
                "network_bytes_sent_per_sec": net_s,
                "network_bytes_recv_per_sec": net_r,
                "network_errors":           net_err,
                "process_count":            procs,
                "system_uptime_seconds":    uptime,
                "event_log_errors_last_min": ev_errs,
                "_anomaly":                 anomaly,
            })

    rows.sort(key=lambda r: r["timestamp"])
    return rows


# ---------------------------------------------------------------------------
# Source 7: GCP Cloud Metrics (CSV)
# ---------------------------------------------------------------------------

GCP_FIELDNAMES = [
    "timestamp", "project_id", "resource_type", "resource_id", "zone",
    "metric_name", "metric_value", "metric_unit",
    "cpu_usage_percent", "memory_usage_bytes", "memory_limit_bytes",
    "network_ingress_bytes", "network_egress_bytes", "restart_count",
    "label_app", "label_env", "label_version", "_anomaly",
]

MEM_LIMIT = 1073741824  # 1 GB

def build_gcp_metrics() -> list:
    rows = []
    restart_count = 0

    for t in minutes_range(BASE_DATE, END_DATE, step_minutes=1):
        elapsed_secs = (t - BASE_DATE).total_seconds()
        container = container_at(t)
        anomaly = None

        # Determine memory / CPU using same logic as Prometheus
        if t < A3_START:
            heap      = int(jitter(314572800, 0.03))
            cpu_frac  = round(jitter(0.08, 0.10), 4)
        elif A3_START <= t < A4_START:
            anomaly   = "A3"
            progress  = min(1.0, (t - A3_START).total_seconds() / (90 * 60))
            heap      = int(314572800 + progress * (1040187392 - 314572800))
            gc_p      = max(0.0, (heap - 500000000) / (MEM_LIMIT - 500000000))
            cpu_frac  = round(min(0.98, 0.08 + gc_p * 0.86), 4)
        elif A4_START <= t < A4_START + timedelta(seconds=15):
            anomaly   = "A4"
            restart_count = 1
            heap = 0; cpu_frac = 0.0
        elif A4_START + timedelta(seconds=15) <= t < A4_START + timedelta(minutes=3, seconds=40):
            anomaly   = "A4"
            progress  = (t - (A4_START + timedelta(seconds=15))).total_seconds() / (3 * 60 + 25)
            heap      = int(314572800 + progress * (1040187392 - 314572800))
            gc_p      = max(0.0, (heap - 500000000) / (MEM_LIMIT - 500000000))
            cpu_frac  = round(min(0.98, 0.08 + gc_p * 0.86), 4)
        elif A4_START + timedelta(minutes=3, seconds=40) <= t < A4_START + timedelta(minutes=3, seconds=55):
            anomaly   = "A4"
            restart_count = 2
            heap = 0; cpu_frac = 0.0
        else:
            heap      = int(jitter(314572800 + 50000000, 0.03))
            cpu_frac  = round(jitter(0.09, 0.10), 4)

        if heap == 0:
            continue  # no metrics while container is down

        net_in  = int(jitter(204800, 0.15))
        net_out = int(jitter(102400, 0.15))

        # Container metric
        rows.append({
            "timestamp":           ts(t),
            "project_id":          GCP_PROJECT,
            "resource_type":       "gke_container",
            "resource_id":         POD_NAME,
            "zone":                GCP_ZONE,
            "metric_name":         "container/cpu/usage_time",
            "metric_value":        round(cpu_frac, 4),
            "metric_unit":         "s{CPU}",
            "cpu_usage_percent":   round(cpu_frac * 100, 2),
            "memory_usage_bytes":  heap,
            "memory_limit_bytes":  MEM_LIMIT,
            "network_ingress_bytes": net_in,
            "network_egress_bytes":  net_out,
            "restart_count":       restart_count,
            "label_app":           SVC_NAME,
            "label_env":           "prod-sim",
            "label_version":       "2.7.0",
            "_anomaly":            anomaly,
        })

        # Cloud SQL metric
        sql_cpu = round(jitter(0.05, 0.15), 4)
        rows.append({
            "timestamp":           ts(t),
            "project_id":          GCP_PROJECT,
            "resource_type":       "cloud_sql_instance",
            "resource_id":         SQL_INSTANCE,
            "zone":                GCP_ZONE,
            "metric_name":         "cloudsql/database/cpu/usage_time",
            "metric_value":        sql_cpu,
            "metric_unit":         "s{CPU}",
            "cpu_usage_percent":   round(sql_cpu * 100, 2),
            "memory_usage_bytes":  None,
            "memory_limit_bytes":  None,
            "network_ingress_bytes": None,
            "network_egress_bytes":  None,
            "restart_count":       0,
            "label_app":           "terminal-handler-db",
            "label_env":           "prod-sim",
            "label_version":       "",
            "_anomaly":            None,
        })

    rows.sort(key=lambda r: r["timestamp"])
    return rows


# ---------------------------------------------------------------------------
# Writers
# ---------------------------------------------------------------------------

def write_json(data: list, filename: str):
    path = os.path.join(OUTPUT_DIR, filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)
    print(f"  Written {len(data):>7,} records → {path}")


def write_csv(data: list, fieldnames: list, filename: str):
    path = os.path.join(OUTPUT_DIR, filename)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(data)
    print(f"  Written {len(data):>7,} records → {path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    ensure_output()
    print("\n=== Synthetic Data Generator — Log Aggregation Platform ===\n")

    print("[1/7] ATM Application Log ...")
    write_json(build_atm_app_log(), "atm_application_log.json")

    print("[2/7] ATM Hardware Sensor Log ...")
    write_json(build_hardware_log(), "atm_hardware_sensor_log.json")

    print("[3/7] Terminal Handler Application Log ...")
    write_json(build_th_app_log(), "terminal_handler_app_log.json")

    print("[4/7] Kafka ATM Metrics Stream ...")
    write_json(build_kafka_stream(), "kafka_atm_metrics_stream.json")

    print("[5/7] Prometheus Metrics ...")
    write_csv(build_prometheus_metrics(), PROM_FIELDNAMES, "prometheus_metrics.csv")

    print("[6/7] Windows OS Metrics ...")
    write_csv(build_windows_os_metrics(), WIN_FIELDNAMES, "windows_os_metrics.csv")

    print("[7/7] GCP Cloud Metrics ...")
    write_csv(build_gcp_metrics(), GCP_FIELDNAMES, "gcp_cloud_metrics.csv")

    print("\n=== Generation Complete ===")
    print(f"Output directory: ./{OUTPUT_DIR}/")
    print("\nAnomaly summary:")
    print("  A1  Network timeout cascade     ATM-GB-0003 @ 10:00")
    print("  A2  Cash cassette depletion     ATM-GB-0003 @ 09:00-09:59")
    print("  A3  JVM memory leak → OOM       Terminal Handler @ 08:00-09:30")
    print("  A4  Container restart loop      Terminal Handler @ 09:30-09:34")
    print("  A5  High response time + drop   ATM-GB-0001 @ 09:30-09:31")
    print("  A6  OS memory pressure → timeout ATM-GB-0002 @ 08:45-10:00")
    print("  A7  Malformed/OOO Kafka events  ATM-GB-0004 @ 08:14-08:15")
    print("\nAll anomalies are tagged with '_anomaly' field for validation.")
    print("All other records have '_anomaly': null and are clean/error-free.\n")


if __name__ == "__main__":
    main()