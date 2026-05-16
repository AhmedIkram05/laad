"""Anomaly injection functions for continuous generator.

Each injector receives a Kafka producer and a datetime. A3 and A6
throttle to one message per invocation to simulate real-time generation
over 90 and 120 ticks respectively. A1, A2, A4, A5, A7 produce their
full signal cascade in a single call (matches real-world burst behavior).
"""
from __future__ import annotations
import random
from uuid import uuid4
from datetime import datetime, timedelta, timezone

from backend.generator.config import ATMS, ATM_LOCATIONS

_anomaly_state: dict[str, dict] = {}


def _get_progressive_state(key: str) -> dict:
    """Returns the active progressive anomaly state for a key."""
    if key not in _anomaly_state:
        _anomaly_state[key] = {"atm": random.choice(ATMS), "corr_id": str(uuid4()), "produced": 0}
    return _anomaly_state[key]


def inject_a1(producer, t: datetime) -> str | None:
    """Inject A1 Network Timeout Cascade.

    Fires cascade across ATM_APP, KAFKA, and TERMINAL_HANDLER sharing correlation_id corr-0030-nnet-disc-0001.
    Exact signal patterns per guide:
      - ATM_APP: NETWORK_DISCONNECT → error_code=ERR-0040
      - ATM_APP: TIMEOUT with response_time_ms=30000
      - Kafka: atm_status=Offline, transaction_failure_reason=HOST_UNAVAILABLE
      - Terminal Handler: NETWORK_TIMEOUT for ATM
    Returns the ATM ID used.
    """
    atm = random.choice(ATMS)
    corr_id = "corr-0030-nnet-disc-0001"
    loc = ATM_LOCATIONS[atm]

    producer.send_event({
        "timestamp": t.isoformat(), "source": "ATM_APP", "atm_id": atm,
        "event_type": "NETWORK_DISCONNECT", "severity": "ERROR",
        "message": "Network connection lost",
        "payload": {"_anomaly_tag": "A1", "location_code": loc, "error_code": "ERR-0040"},
        "correlation_id": corr_id,
        "message_id": str(uuid4()),
    })

    producer.send_event({
        "timestamp": (t + timedelta(seconds=5)).isoformat(), "source": "ATM_APP",
        "atm_id": atm, "event_type": "TIMEOUT", "severity": "ERROR",
        "message": "Request timed out",
        "payload": {"_anomaly_tag": "A1", "error_code": "ERR-0040", "response_time_ms": 30000},
        "correlation_id": corr_id,
        "message_id": str(uuid4()),
    })

    producer.send_event({
        "timestamp": (t + timedelta(seconds=10)).isoformat(), "source": "KAFKA",
        "atm_id": atm, "event_type": "STATUS", "severity": "INFO",
        "message": "ATM Offline",
        "payload": {"_anomaly_tag": "A1", "atm_status": "Offline", "transaction_failure_reason": "HOST_UNAVAILABLE"},
        "correlation_id": corr_id,
        "message_id": str(uuid4()),
    })

    producer.send_event({
        "timestamp": (t + timedelta(seconds=15)).isoformat(), "source": "TERMINAL_HANDLER",
        "atm_id": atm, "event_type": "NETWORK_TIMEOUT", "severity": "FATAL",
        "message": "Connection timed out",
        "payload": {"_anomaly_tag": "A1"},
        "correlation_id": corr_id,
        "message_id": str(uuid4()),
    })
    return atm


def inject_a2(producer, t: datetime) -> str | None:
    """Inject A2 Cash Cassette Depletion → Out of Service.

    Exact signal patterns per guide:
      - Hardware: CASSETTE_LOW (severity=WARNING) × 2 cassettes
      - Hardware: CASSETTE_EMPTY (severity=CRITICAL) × 2 cassettes
      - Kafka: atm_status="Out of Service", transaction_failure_reason="CASH_DISPENSE_ERROR"
      - Kafka: transaction_rate_tps=0.0, transaction_success_rate=0.0
    Returns the ATM ID used.
    """
    atm = random.choice(ATMS)
    corr_id = str(uuid4())

    producer.send_event({
        "timestamp": t.isoformat(), "source": "HARDWARE", "atm_id": atm,
        "event_type": "CASSETTE_LOW", "severity": "WARNING",
        "message": "Cash low in cassette 1",
        "payload": {"_anomaly_tag": "A2", "cassette_id": 1},
        "correlation_id": corr_id,
        "message_id": str(uuid4()),
    })
    producer.send_event({
        "timestamp": t.isoformat(), "source": "HARDWARE", "atm_id": atm,
        "event_type": "CASSETTE_LOW", "severity": "WARNING",
        "message": "Cash low in cassette 2",
        "payload": {"_anomaly_tag": "A2", "cassette_id": 2},
        "correlation_id": corr_id,
        "message_id": str(uuid4()),
    })

    producer.send_event({
        "timestamp": (t + timedelta(minutes=5)).isoformat(), "source": "HARDWARE",
        "atm_id": atm, "event_type": "CASSETTE_EMPTY", "severity": "CRITICAL",
        "message": "Cash empty in cassette 1",
        "payload": {"_anomaly_tag": "A2", "cassette_id": 1},
        "correlation_id": corr_id,
        "message_id": str(uuid4()),
    })
    producer.send_event({
        "timestamp": (t + timedelta(minutes=5)).isoformat(), "source": "HARDWARE",
        "atm_id": atm, "event_type": "CASSETTE_EMPTY", "severity": "CRITICAL",
        "message": "Cash empty in cassette 2",
        "payload": {"_anomaly_tag": "A2", "cassette_id": 2},
        "correlation_id": corr_id,
        "message_id": str(uuid4()),
    })

    producer.send_event({
        "timestamp": (t + timedelta(minutes=8)).isoformat(), "source": "KAFKA",
        "atm_id": atm, "event_type": "STATUS", "severity": "INFO",
        "message": "ATM Out of Service",
        "payload": {
            "_anomaly_tag": "A2",
            "atm_status": "Out of Service",
            "transaction_failure_reason": "CASH_DISPENSE_ERROR",
            "transaction_rate_tps": 0.0,
            "transaction_success_rate": 0.0,
        },
        "correlation_id": corr_id,
        "message_id": str(uuid4()),
    })
    return atm


def inject_a3(producer, t: datetime) -> str | None:
    """Inject A3 JVM Memory Leak → OOM.

    Exact signal patterns per guide (90-minute window):
      - Prometheus: jvm_memory_used_bytes rising: 300MB → 1040MB (monotonic)
      - Prometheus: jvm_gc_pause_seconds_sum: 0.45s → 24.7s (GC thrashing)
      - Prometheus: process_cpu_usage rising to 0.94 (94%)
      - GCP: container/cpu/usage_time rising to 94%
      - Terminal Handler: OutOfMemoryError FATAL event
    Returns the ATM ID used.
    """
    atm = random.choice(ATMS)
    corr_id = str(uuid4())
    pod_name = f"terminal-handler-{atm.lower()}"

    jvm_start = 300_000_000
    jvm_end = 1_040_000_000
    jvm_step = (jvm_end - jvm_start) / 90

    gc_start = 0.45
    gc_end = 24.7
    gc_step = (gc_end - gc_start) / 90

    for i in range(90):
        tick_t = t - timedelta(minutes=90 - i)
        jvm_mem = jvm_start + (i * jvm_step)
        producer.send_metric({
            "timestamp": tick_t.isoformat(), "source": "PROMETHEUS",
            "entity_id": atm, "metric_name": "jvm_memory_used_bytes",
            "metric_value": jvm_mem,
            "payload": {"_anomaly_tag": "A3", "pod_name": pod_name},
            "correlation_id": corr_id,
            "message_id": str(uuid4()),
        })

        gc_pause = gc_start + (i * gc_step)
        producer.send_metric({
            "timestamp": tick_t.isoformat(), "source": "PROMETHEUS",
            "entity_id": atm, "metric_name": "jvm_gc_pause_seconds_sum",
            "metric_value": gc_pause,
            "payload": {"_anomaly_tag": "A3", "pod_name": pod_name},
            "correlation_id": corr_id,
            "message_id": str(uuid4()),
        })

        cpu_usage = 0.94
        producer.send_metric({
            "timestamp": tick_t.isoformat(), "source": "PROMETHEUS",
            "entity_id": atm, "metric_name": "process_cpu_usage",
            "metric_value": cpu_usage,
            "payload": {"_anomaly_tag": "A3", "pod_name": pod_name},
            "correlation_id": corr_id,
            "message_id": str(uuid4()),
        })

        producer.send_metric({
            "timestamp": tick_t.isoformat(), "source": "CLOUD",
            "entity_id": atm, "metric_name": "container/cpu/usage_time",
            "metric_value": 94.0,
            "payload": {"_anomaly_tag": "A3", "pod_name": pod_name},
            "correlation_id": corr_id,
            "message_id": str(uuid4()),
        })

    producer.send_event({
        "timestamp": t.isoformat(), "source": "TERMINAL_HANDLER",
        "atm_id": atm, "event_type": "OutOfMemoryError", "severity": "FATAL",
        "message": "Java heap space",
        "payload": {"_anomaly_tag": "A3", "pod_name": pod_name},
        "correlation_id": corr_id,
        "message_id": str(uuid4()),
    })
    return atm


def inject_a4(producer, t: datetime) -> str | None:
    """Inject A4 Container Restart Loop.

    Exact signal patterns per guide:
      - GCP: container/restart_count = 1, then 2 within 4 minutes
      - Terminal Handler: STARTUP repeated 3× (container_id changes each time)
      - Terminal Handler: Two FATAL OutOfMemoryError events
    Returns the ATM ID used.
    """
    atm = random.choice(ATMS)
    corr_id = str(uuid4())
    pod_name = f"terminal-handler-{atm.lower()}"

    producer.send_event({
        "timestamp": t.isoformat(), "source": "TERMINAL_HANDLER", "atm_id": atm,
        "event_type": "STARTUP", "severity": "INFO",
        "message": "Pod starting",
        "payload": {"_anomaly_tag": "A4", "pod_name": pod_name, "container_id": "container-abc123"},
        "correlation_id": corr_id,
        "message_id": str(uuid4()),
    })

    producer.send_metric({
        "timestamp": (t + timedelta(minutes=2)).isoformat(), "source": "CLOUD",
        "entity_id": atm, "metric_name": "container/restart_count",
        "metric_value": 1,
        "payload": {"_anomaly_tag": "A4", "pod_name": pod_name},
        "correlation_id": corr_id,
        "message_id": str(uuid4()),
    })

    producer.send_event({
        "timestamp": (t + timedelta(minutes=2, seconds=30)).isoformat(), "source": "TERMINAL_HANDLER",
        "atm_id": atm, "event_type": "OutOfMemoryError", "severity": "FATAL",
        "message": "Java heap space",
        "payload": {"_anomaly_tag": "A4", "pod_name": pod_name},
        "correlation_id": corr_id,
        "message_id": str(uuid4()),
    })

    producer.send_event({
        "timestamp": (t + timedelta(minutes=3)).isoformat(), "source": "TERMINAL_HANDLER", "atm_id": atm,
        "event_type": "STARTUP", "severity": "INFO",
        "message": "Pod restarting",
        "payload": {"_anomaly_tag": "A4", "pod_name": pod_name, "container_id": "container-def456"},
        "correlation_id": corr_id,
        "message_id": str(uuid4()),
    })

    producer.send_metric({
        "timestamp": (t + timedelta(minutes=4)).isoformat(), "source": "CLOUD",
        "entity_id": atm, "metric_name": "container/restart_count",
        "metric_value": 2,
        "payload": {"_anomaly_tag": "A4", "pod_name": pod_name},
        "correlation_id": corr_id,
        "message_id": str(uuid4()),
    })

    producer.send_event({
        "timestamp": (t + timedelta(minutes=4)).isoformat(), "source": "TERMINAL_HANDLER",
        "atm_id": atm, "event_type": "OutOfMemoryError", "severity": "FATAL",
        "message": "Java heap space",
        "payload": {"_anomaly_tag": "A4", "pod_name": pod_name},
        "correlation_id": corr_id,
        "message_id": str(uuid4()),
    })

    producer.send_event({
        "timestamp": (t + timedelta(minutes=4, seconds=30)).isoformat(), "source": "TERMINAL_HANDLER", "atm_id": atm,
        "event_type": "STARTUP", "severity": "INFO",
        "message": "Pod restarting",
        "payload": {"_anomaly_tag": "A4", "pod_name": pod_name, "container_id": "container-ghi789"},
        "correlation_id": corr_id,
        "message_id": str(uuid4()),
    })
    return atm


def inject_a5(producer, t: datetime) -> str | None:
    """Inject A5 High Response Time Spike + Success Rate Drop.

    Exact signal patterns per guide:
      - Kafka: response_time_ms = 3200ms then 30000ms (normal: ~290ms)
      - Kafka: transaction_success_rate drops: 100% → 72% → 50%
      - Kafka: failure_count = 8, then 14
      - ATM App: event_type=TIMEOUT with error_code=ERR-0012
      - Correlation IDs: corr-0010-xxyy-aabb-1234, corr-0011-xyzw-ccdd-5678
    Returns the ATM ID used.
    """
    atm = random.choice(ATMS)
    corr_ids = ["corr-0010-xxyy-aabb-1234", "corr-0011-xyzw-ccdd-5678"]

    producer.send_event({
        "timestamp": t.isoformat(), "source": "KAFKA", "atm_id": atm,
        "event_type": "METRIC", "severity": "INFO",
        "message": "Latency update",
        "payload": {
            "_anomaly_tag": "A5",
            "response_time_ms": 3200,
            "transaction_success_rate": 100,
            "failure_count": 0,
        },
        "correlation_id": corr_ids[0],
        "message_id": str(uuid4()),
    })

    producer.send_event({
        "timestamp": (t + timedelta(seconds=10)).isoformat(), "source": "KAFKA", "atm_id": atm,
        "event_type": "METRIC", "severity": "INFO",
        "message": "Latency update",
        "payload": {
            "_anomaly_tag": "A5",
            "response_time_ms": 4500,
            "transaction_success_rate": 72,
            "failure_count": 8,
        },
        "correlation_id": corr_ids[0],
        "message_id": str(uuid4()),
    })

    producer.send_event({
        "timestamp": (t + timedelta(seconds=20)).isoformat(), "source": "KAFKA", "atm_id": atm,
        "event_type": "METRIC", "severity": "INFO",
        "message": "Latency update",
        "payload": {
            "_anomaly_tag": "A5",
            "response_time_ms": 30000,
            "transaction_success_rate": 50,
            "failure_count": 14,
        },
        "correlation_id": corr_ids[1],
        "message_id": str(uuid4()),
    })

    producer.send_event({
        "timestamp": (t + timedelta(seconds=25)).isoformat(), "source": "ATM_APP", "atm_id": atm,
        "event_type": "TIMEOUT", "severity": "ERROR",
        "message": "Request timed out",
        "payload": {"_anomaly_tag": "A5", "error_code": "ERR-0012"},
        "correlation_id": corr_ids[1],
        "message_id": str(uuid4()),
    })

    producer.send_event({
        "timestamp": (t + timedelta(seconds=30)).isoformat(), "source": "KAFKA", "atm_id": atm,
        "event_type": "STATUS", "severity": "WARNING",
        "message": "Success rate drop detected",
        "payload": {"_anomaly_tag": "A5", "transaction_success_rate": 50, "failure_count": 14},
        "correlation_id": corr_ids[1],
        "message_id": str(uuid4()),
    })
    return atm


def inject_a6(producer, t: datetime) -> str | None:
    """Inject A6 OS Memory Pressure → Application Timeout.

    Exact signal patterns per guide (120-minute window):
      - Windows OS: memory_usage_percent: 46% → 98.75% (over 2 hours)
      - Windows OS: network_errors growing: 0 → 22
      - Windows OS: cpu_usage_percent rising to 91.5%
      - ATM App: event_type=TIMEOUT with error_detail containing "ThreadAbortException"
    Returns the ATM ID used.
    """
    atm = random.choice(ATMS)
    corr_id = str(uuid4())
    loc = ATM_LOCATIONS[atm]

    mem_start = 46.0
    mem_end = 98.75
    mem_step = (mem_end - mem_start) / 120

    net_err_start = 0
    net_err_end = 22
    net_err_step = (net_err_end - net_err_start) / 120

    for i in range(120):
        tick_t = t - timedelta(minutes=120 - i)
        mem_val = mem_start + (i * mem_step)
        producer.send_metric({
            "timestamp": tick_t.isoformat(), "source": "OS",
            "entity_id": atm, "metric_name": "memory_usage_percent",
            "metric_value": mem_val,
            "payload": {"_anomaly_tag": "A6", "location_code": loc},
            "correlation_id": corr_id,
            "message_id": str(uuid4()),
        })

        net_err_val = net_err_start + (i * net_err_step)
        producer.send_metric({
            "timestamp": tick_t.isoformat(), "source": "OS",
            "entity_id": atm, "metric_name": "network_errors",
            "metric_value": net_err_val,
            "payload": {"_anomaly_tag": "A6"},
            "correlation_id": corr_id,
            "message_id": str(uuid4()),
        })

        cpu_val = 20 + (i * 0.596)
        producer.send_metric({
            "timestamp": tick_t.isoformat(), "source": "OS",
            "entity_id": atm, "metric_name": "cpu_usage_percent",
            "metric_value": cpu_val,
            "payload": {"_anomaly_tag": "A6"},
            "correlation_id": corr_id,
            "message_id": str(uuid4()),
        })

    producer.send_event({
        "timestamp": t.isoformat(), "source": "ATM_APP",
        "atm_id": atm, "event_type": "TIMEOUT", "severity": "ERROR",
        "message": "OS resource timeout - ThreadAbortException",
        "payload": {
            "_anomaly_tag": "A6",
            "error_code": "ERR-MEM",
            "error_detail": "ThreadAbortException: Thread was being aborted due to memory pressure",
        },
        "correlation_id": corr_id,
        "message_id": str(uuid4()),
    })
    return atm


def inject_a7(producer, t: datetime) -> str | None:
    """Inject A7 Malformed / Out-of-Order Kafka Events.

    Exact signal patterns per guide:
      - Kafka offset 4050: earlier timestamp than expected (out-of-order)
      - Kafka offset 4051: atm_status=null, transaction_rate_tps=null (missing fields)
      - Prometheus: metric_value=890iembre (non-numeric - malformed)
    Returns the ATM ID used.
    """
    atm = random.choice(ATMS)
    corr_id = str(uuid4())

    producer.send_event({
        "timestamp": (t - timedelta(minutes=5)).isoformat(), "source": "KAFKA", "atm_id": atm,
        "event_type": "METRIC", "severity": "INFO",
        "message": "Kafka metrics",
        "payload": {
            "_anomaly_tag": "A7_OUT_OF_ORDER",
            "offset": 4050,
            "atm_status": "Online",
            "transaction_rate_tps": 15.5,
        },
        "correlation_id": corr_id,
        "message_id": str(uuid4()),
    })

    producer.send_event({
        "timestamp": t.isoformat(), "source": "KAFKA", "atm_id": atm,
        "event_type": "METRIC", "severity": "INFO",
        "message": "Kafka metrics - out of order",
        "payload": {
            "_anomaly_tag": "A7_OUT_OF_ORDER",
            "offset": 4051,
            "atm_status": None,
            "transaction_rate_tps": None,
        },
        "correlation_id": corr_id,
        "message_id": str(uuid4()),
    })

    producer.send_metric({
        "timestamp": t.isoformat(), "source": "PROMETHEUS",
        "entity_id": atm, "metric_name": "jvm_memory_used_bytes",
        "metric_value": "890iembre",
        "payload": {"_anomaly_tag": "A7_MALFORMED"},
        "correlation_id": corr_id,
        "message_id": str(uuid4()),
    })
    return atm


ANOMALY_REGISTRY = [
    ("A1", inject_a1, 300),
    ("A2", inject_a2, 600),
    ("A3", inject_a3, 3600),
    ("A4", inject_a4, 300),
    ("A5", inject_a5, 300),
    ("A6", inject_a6, 3600),
    ("A7", inject_a7, 300),
]
