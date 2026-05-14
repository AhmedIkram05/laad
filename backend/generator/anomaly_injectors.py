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


def inject_a1(producer, t: datetime) -> None:
    """Inject A1 Network Timeout Cascade.

    Fires a 4-message cascade across ATM_APP, KAFKA, and TERMINAL_HANDLER
    sharing a single correlation_id.
    """
    atm = random.choice(ATMS)
    corr_id = str(uuid4())
    producer.send_event({
        "timestamp": t.isoformat(), "source": "ATM_APP", "atm_id": atm,
        "event_type": "NETWORK_DISCONNECT", "severity": "ERROR",
        "message": "Network connection lost",
        "payload": {"_anomaly_tag": "A1", "location_code": ATM_LOCATIONS[atm]},
        "correlation_id": corr_id,
    })
    producer.send_event({
        "timestamp": (t + timedelta(seconds=5)).isoformat(), "source": "ATM_APP",
        "atm_id": atm, "event_type": "TIMEOUT", "severity": "ERROR",
        "message": "Request timed out",
        "payload": {"_anomaly_tag": "A1"},
        "correlation_id": corr_id,
    })
    producer.send_event({
        "timestamp": (t + timedelta(seconds=10)).isoformat(), "source": "KAFKA",
        "atm_id": atm, "event_type": "STATUS", "severity": "INFO",
        "message": "ATM Offline",
        "payload": {"_anomaly_tag": "A1", "atm_status": "Offline"},
        "correlation_id": corr_id,
    })
    producer.send_event({
        "timestamp": (t + timedelta(seconds=15)).isoformat(), "source": "TERMINAL_HANDLER",
        "atm_id": atm, "event_type": "NETWORK_ERROR", "severity": "FATAL",
        "message": "Connection timed out",
        "payload": {"_anomaly_tag": "A1"},
        "correlation_id": corr_id,
    })


def inject_a2(producer, t: datetime) -> None:
    """Inject A2 Cash Cassette Empty.

    Fires a 3-message cascade across HARDWARE and KAFKA sharing a
    single correlation_id. The CASSETTE_EMPTY fires 5 min after CASSETTE_LOW.
    """
    atm = random.choice(ATMS)
    corr_id = str(uuid4())
    producer.send_event({
        "timestamp": t.isoformat(), "source": "HARDWARE", "atm_id": atm,
        "event_type": "CASSETTE_LOW", "severity": "WARNING",
        "message": "Cash low in cassette 1",
        "payload": {"_anomaly_tag": "A2"},
        "correlation_id": corr_id,
    })
    producer.send_event({
        "timestamp": (t + timedelta(minutes=5)).isoformat(), "source": "HARDWARE",
        "atm_id": atm, "event_type": "CASSETTE_EMPTY", "severity": "CRITICAL",
        "message": "Cash empty in cassette 1",
        "payload": {"_anomaly_tag": "A2"},
        "correlation_id": corr_id,
    })
    producer.send_event({
        "timestamp": (t + timedelta(minutes=10)).isoformat(), "source": "KAFKA",
        "atm_id": atm, "event_type": "STATUS", "severity": "INFO",
        "message": "ATM Out of Service",
        "payload": {"_anomaly_tag": "A2", "atm_status": "OutOfService"},
        "correlation_id": corr_id,
    })


def inject_a3(producer, t: datetime) -> None:
    """Inject A3 JVM Memory Leak.

    State-based progressive emission — one message per call across 90 ticks.
    Produces monotonically rising JVM heap and GC pause metrics, terminating
    with a TERMINAL_HANDLER OOM_ERROR on the 90th call.
    """
    atm_key = "a3"
    state = _get_progressive_state(atm_key)

    if state["produced"] >= 90:
        del _anomaly_state[atm_key]
        return

    i = state["produced"]
    state["produced"] += 1
    tick_t = t + timedelta(minutes=i)

    producer.send_metric({
        "timestamp": tick_t.isoformat(), "source": "PROMETHEUS",
        "entity_id": state["atm"], "metric_name": "jvm_memory_used_bytes",
        "metric_value": 1e8 + (i * 1e7),
        "payload": {"_anomaly_tag": "A3"},
        "correlation_id": state["corr_id"],
    })
    gc_pause = min(5.0, i * 0.05)
    producer.send_metric({
        "timestamp": tick_t.isoformat(), "source": "PROMETHEUS",
        "entity_id": state["atm"], "metric_name": "jvm_gc_pause_seconds_sum",
        "metric_value": gc_pause,
        "payload": {"_anomaly_tag": "A3"},
        "correlation_id": state["corr_id"],
    })
    cpu_usage = min(95.0, 20 + (i * 0.8))
    producer.send_metric({
        "timestamp": tick_t.isoformat(), "source": "CLOUD",
        "entity_id": state["atm"], "metric_name": "container/cpu/usage_time",
        "metric_value": cpu_usage,
        "payload": {"_anomaly_tag": "A3"},
        "correlation_id": state["corr_id"],
    })

    if state["produced"] == 90:
        producer.send_event({
            "timestamp": tick_t.isoformat(), "source": "TERMINAL_HANDLER",
            "atm_id": state["atm"], "event_type": "OOM_ERROR", "severity": "FATAL",
            "message": "Java heap space",
            "payload": {"_anomaly_tag": "A3"},
            "correlation_id": state["corr_id"],
        })
        del _anomaly_state[atm_key]


def inject_a4(producer, t: datetime) -> None:
    """Inject A4 Container Restart Loop.

    Fires a 3-message cascade: STARTUP → CRASH → STARTUP within 60 seconds,
    simulating a pod restart loop.
    """
    atm = random.choice(ATMS)
    corr_id = str(uuid4())
    producer.send_event({
        "timestamp": t.isoformat(), "source": "TERMINAL_HANDLER", "atm_id": atm,
        "event_type": "STARTUP", "severity": "INFO",
        "message": "Pod starting",
        "payload": {"_anomaly_tag": "A4"},
        "correlation_id": corr_id,
    })
    producer.send_event({
        "timestamp": (t + timedelta(seconds=30)).isoformat(), "source": "TERMINAL_HANDLER",
        "atm_id": atm, "event_type": "CRASH", "severity": "ERROR",
        "message": "Unexpected exit",
        "payload": {"_anomaly_tag": "A4"},
        "correlation_id": corr_id,
    })
    producer.send_event({
        "timestamp": (t + timedelta(seconds=60)).isoformat(), "source": "TERMINAL_HANDLER",
        "atm_id": atm, "event_type": "STARTUP", "severity": "INFO",
        "message": "Pod restarting",
        "payload": {"_anomaly_tag": "A4"},
        "correlation_id": corr_id,
    })


def inject_a5(producer, t: datetime) -> None:
    """Inject A5 High Response Time Spike.

    Fires 11 messages over 90 seconds with progressively degrading success
    rate (from 1.0 to ~0.3) and response times > 5000ms.
    """
    atm = random.choice(ATMS)
    corr_id = str(uuid4())
    success_rate = 1.0
    for i in range(10):
        tick_t = t + timedelta(seconds=i * 10)
        success_rate = max(0.3, success_rate - random.uniform(0.05, 0.15))
        producer.send_event({
            "timestamp": tick_t.isoformat(), "source": "KAFKA", "atm_id": atm,
            "event_type": "METRIC", "severity": "INFO",
            "message": "Latency update",
            "payload": {
                "_anomaly_tag": "A5",
                "response_time_ms": 5000 + random.randint(0, 1000),
                "success_rate": round(success_rate, 3),
            },
            "correlation_id": corr_id,
        })
    producer.send_event({
        "timestamp": (t + timedelta(seconds=90)).isoformat(), "source": "KAFKA",
        "atm_id": atm, "event_type": "STATUS", "severity": "WARNING",
        "message": "Success rate drop detected",
        "payload": {"_anomaly_tag": "A5", "success_rate": round(success_rate, 3)},
        "correlation_id": corr_id,
    })


def inject_a6(producer, t: datetime) -> None:
    """Inject A6 OS Memory Pressure.

    State-based progressive emission — one message per call across 120 ticks.
    Produces monotonically rising OS memory usage (20 → 90%), terminating
    with an ATM_APP TIMEOUT on the 120th call.
    """
    atm_key = "a6"
    state = _get_progressive_state(atm_key)

    if state["produced"] >= 120:
        del _anomaly_state[atm_key]
        return

    i = state["produced"]
    state["produced"] += 1
    tick_t = t + timedelta(minutes=i)

    producer.send_metric({
        "timestamp": tick_t.isoformat(), "source": "OS",
        "entity_id": state["atm"], "metric_name": "windows_os_snapshot",
        "metric_value": 20 + (i * 1.2),
        "payload": {"_anomaly_tag": "A6"},
        "correlation_id": state["corr_id"],
    })

    if state["produced"] == 120:
        producer.send_event({
            "timestamp": tick_t.isoformat(), "source": "ATM_APP",
            "atm_id": state["atm"], "event_type": "TIMEOUT", "severity": "ERROR",
            "message": "OS resource timeout",
            "payload": {"_anomaly_tag": "A6"},
            "correlation_id": state["corr_id"],
        })
        del _anomaly_state[atm_key]


def inject_a7(producer, t: datetime) -> None:
    """Inject A7 Out-of-Order Kafka Events.

    Fires a single malformed KAFKA event with offset=-1 and
    _anomaly_tag=A7_OUT_OF_ORDER.
    """
    atm = random.choice(ATMS)
    producer.send_event({
        "timestamp": t.isoformat(), "source": "KAFKA", "atm_id": atm,
        "event_type": "METRIC", "severity": "INFO",
        "message": "Malformed event",
        "payload": {"_anomaly_tag": "A7_OUT_OF_ORDER", "offset": -1},
        "correlation_id": str(uuid4()),
    })


ANOMALY_REGISTRY = [
    ("A1", inject_a1, 300),
    ("A2", inject_a2, 600),
    ("A3", inject_a3, 3600),
    ("A4", inject_a4, 300),
    ("A5", inject_a5, 300),
    ("A6", inject_a6, 3600),
    ("A7", inject_a7, 300),
]
