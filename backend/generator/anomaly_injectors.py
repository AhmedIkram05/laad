"""Anomaly injection functions for continuous generator."""
from __future__ import annotations
import random
import uuid
from datetime import datetime, timedelta
import psycopg2.extras
from backend.generator.emitters import insert_event, insert_metric
from backend.generator.config import ATMS, ATM_LOCATIONS

def inject_a1(cur, t):
    """NETWORK_DISCONNECT + TIMEOUT cascade."""
    atm = random.choice(ATMS)
    corr_id = str(uuid.uuid4())
    # ATM_APP
    insert_event(cur, t, "ATM_APP", atm, "NETWORK_DISCONNECT", "ERROR", "Network connection lost", {"_anomaly_tag": "A1", "location_code": ATM_LOCATIONS[atm]}, correlation_id=corr_id)
    insert_event(cur, t + timedelta(seconds=5), "ATM_APP", atm, "TIMEOUT", "ERROR", "Request timed out", {"_anomaly_tag": "A1"}, correlation_id=corr_id)
    # KAFKA
    insert_event(cur, t + timedelta(seconds=10), "KAFKA", atm, "STATUS", "INFO", "ATM Offline", {"_anomaly_tag": "A1", "atm_status": "Offline"}, correlation_id=corr_id)
    # TERMINAL_HANDLER
    insert_event(cur, t + timedelta(seconds=15), "TERMINAL_HANDLER", atm, "NETWORK_ERROR", "FATAL", "Connection timed out", {"_anomaly_tag": "A1"}, correlation_id=corr_id)

def inject_a2(cur, t):
    """CASSETTE_LOW -> CASSETTE_EMPTY cascade."""
    atm = random.choice(ATMS)
    corr_id = str(uuid.uuid4())
    insert_event(cur, t, "HARDWARE", atm, "CASSETTE_LOW", "WARNING", "Cash low in cassette 1", {"_anomaly_tag": "A2"}, correlation_id=corr_id)
    insert_event(cur, t + timedelta(minutes=5), "HARDWARE", atm, "CASSETTE_EMPTY", "CRITICAL", "Cash empty in cassette 1", {"_anomaly_tag": "A2"}, correlation_id=corr_id)
    insert_event(cur, t + timedelta(minutes=10), "KAFKA", atm, "STATUS", "INFO", "ATM Out of Service", {"_anomaly_tag": "A2", "atm_status": "OutOfService"}, correlation_id=corr_id)

def inject_a3(cur, t):
    """JVM Memory Leak + GC Pause Escalation + Container CPU Spike over 90 minutes."""
    atm = random.choice(ATMS)
    corr_id = str(uuid.uuid4())
    for i in range(90):
        tick_t = t + timedelta(minutes=i)
        insert_metric(cur, tick_t, "PROMETHEUS", atm, "jvm_memory_used_bytes", 1e8 + (i * 1e7), {"_anomaly_tag": "A3"}, correlation_id=corr_id)
        gc_pause = min(5.0, i * 0.05)
        insert_metric(cur, tick_t, "PROMETHEUS", atm, "jvm_gc_pause_seconds_sum", gc_pause, {"_anomaly_tag": "A3"}, correlation_id=corr_id)
        cpu_usage = min(95.0, 20 + (i * 0.8))
        insert_metric(cur, tick_t, "CLOUD", atm, "container/cpu/usage_time", cpu_usage, {"_anomaly_tag": "A3"}, correlation_id=corr_id)
    insert_event(cur, t + timedelta(minutes=90), "TERMINAL_HANDLER", atm, "OOM_ERROR", "FATAL", "Java heap space", {"_anomaly_tag": "A3"}, correlation_id=corr_id)

def inject_a4(cur, t):
    """Container Restart Sequence."""
    atm = random.choice(ATMS)
    corr_id = str(uuid.uuid4())
    insert_event(cur, t, "TERMINAL_HANDLER", atm, "STARTUP", "INFO", "Pod starting", {"_anomaly_tag": "A4"}, correlation_id=corr_id)
    insert_event(cur, t + timedelta(seconds=30), "TERMINAL_HANDLER", atm, "CRASH", "ERROR", "Unexpected exit", {"_anomaly_tag": "A4"}, correlation_id=corr_id)
    insert_event(cur, t + timedelta(seconds=60), "TERMINAL_HANDLER", atm, "STARTUP", "INFO", "Pod restarting", {"_anomaly_tag": "A4"}, correlation_id=corr_id)

def inject_a5(cur, t):
    """Response Time Spike + Success Rate Drop."""
    atm = random.choice(ATMS)
    corr_id = str(uuid.uuid4())
    success_rate = 1.0
    for i in range(10):
        tick_t = t + timedelta(seconds=i*10)
        success_rate = max(0.3, success_rate - random.uniform(0.05, 0.15))
        insert_event(cur, tick_t, "KAFKA", atm, "METRIC", "INFO", "Latency update", {"_anomaly_tag": "A5", "response_time_ms": 5000 + random.randint(0, 1000), "success_rate": round(success_rate, 3)}, correlation_id=corr_id)
    insert_event(cur, t + timedelta(seconds=90), "KAFKA", atm, "STATUS", "WARNING", "Success rate drop detected", {"_anomaly_tag": "A5", "success_rate": round(success_rate, 3)}, correlation_id=corr_id)

def inject_a6(cur, t):
    """OS Memory Pressure over 120 minutes."""
    atm = random.choice(ATMS)
    corr_id = str(uuid.uuid4())
    for i in range(120):
        tick_t = t + timedelta(minutes=i)
        insert_metric(cur, tick_t, "OS", atm, "windows_os_snapshot", 20 + (i * 1.2), {"_anomaly_tag": "A6"}, correlation_id=corr_id)
    insert_event(cur, t + timedelta(minutes=120), "ATM_APP", atm, "TIMEOUT", "ERROR", "OS resource timeout", {"_anomaly_tag": "A6"}, correlation_id=corr_id)

def inject_a7(cur, t):
    """Malformed Kafka / Out-of-Order."""
    atm = random.choice(ATMS)
    insert_event(cur, t, "KAFKA", atm, "METRIC", "INFO", "Malformed event", {"_anomaly_tag": "A7_OUT_OF_ORDER", "offset": -1}, correlation_id=str(uuid.uuid4()))

ANOMALY_REGISTRY = [
    ("A1", inject_a1, 300),
    ("A2", inject_a2, 600),
    ("A3", inject_a3, 3600),
    ("A4", inject_a4, 300),
    ("A5", inject_a5, 300),
    ("A6", inject_a6, 3600),
    ("A7", inject_a7, 300),
]
