"""Baseline event emitters for continuous generation."""
from __future__ import annotations
import random
import logging
from datetime import datetime
import psycopg2.extras
from backend.generator.config import ATMS, ATM_LOCATIONS, POD_NAME, OS_VERSION

log = logging.getLogger(__name__)

def insert_event(cur, t, source, atm_id, event_type, severity, message, payload, correlation_id=None, transaction_id=None):
    cur.execute(
        "INSERT INTO events (timestamp, source, atm_id, correlation_id, transaction_id, event_type, severity, message, payload) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
        (t, source, atm_id, correlation_id, transaction_id, event_type, severity, message, psycopg2.extras.Json(payload))
    )

def insert_metric(cur, t, source, entity_id, metric_name, metric_value, payload, correlation_id=None):
    if correlation_id:
        payload = dict(payload, correlation_id=correlation_id)
    cur.execute(
        "INSERT INTO metrics (timestamp, source, entity_id, metric_name, metric_value, payload) VALUES (%s, %s, %s, %s, %s, %s)",
        (t, source, entity_id, metric_name, metric_value, psycopg2.extras.Json(payload))
    )

def emit_atm_app_events(cur, t):
    for atm in ATMS:
        if random.random() < 0.35:
            # Normal heartbeat/activity
            insert_event(cur, t, "ATM_APP", atm, "ACTIVITY", "INFO", "User session active", {"location_code": ATM_LOCATIONS[atm]})

def emit_hardware_events(cur, t):
    for atm in ATMS:
        if random.random() < 0.1:
            insert_event(cur, t, "HARDWARE", atm, "DIAGNOSTIC", "INFO", "Cash dispenser health check passed", {"component": "dispenser_v2"})

def emit_terminal_handler_events(cur, t):
    for atm in ATMS:
        if random.random() < 0.2:
            insert_event(cur, t, "TERMINAL_HANDLER", atm, "LOG", "INFO", "Handling request", {"pod": POD_NAME, "os": OS_VERSION})

def emit_kafka_metrics(cur, t):
    for atm in ATMS:
        if random.random() < 0.5:
            # Simulate a metric window
            insert_metric(cur, t, "KAFKA", atm, "kafka_throughput", random.uniform(100, 500), {"correlation_id": None})

def emit_prometheus_metrics(cur, t):
    for atm in ATMS:
        if random.random() < 0.5:
            insert_metric(cur, t, "PROMETHEUS", atm, "jvm_memory_used_bytes", random.uniform(1e8, 5e8), {})

def emit_windows_os_metrics(cur, t):
    for atm in ATMS:
        if random.random() < 0.5:
            insert_metric(cur, t, "OS", atm, "windows_os_snapshot", random.uniform(10, 90), {})

def emit_gcp_metrics(cur, t):
    for atm in ATMS:
        if random.random() < 0.5:
            insert_metric(cur, t, "CLOUD", atm, "container/cpu/usage_time", random.uniform(0.1, 1.0), {})

BASELINE_EMITTERS = [
    emit_atm_app_events,
    emit_hardware_events,
    emit_terminal_handler_events,
    emit_kafka_metrics,
    emit_prometheus_metrics,
    emit_windows_os_metrics,
    emit_gcp_metrics
]
