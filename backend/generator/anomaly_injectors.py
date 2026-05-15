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

    Fires a variable cascade (3-4 signals) across ATM_APP, KAFKA, and TERMINAL_HANDLER
    sharing a single correlation_id.
    Returns the ATM ID used.
    """
    atm = random.choice(ATMS)
    corr_id = str(uuid4())
    
    # Always include the first two signals: NETWORK_DISCONNECT and TIMEOUT
    producer.send_event({
        "timestamp": t.isoformat(), "source": "ATM_APP", "atm_id": atm,
        "event_type": "NETWORK_DISCONNECT", "severity": "ERROR",
        "message": "Network connection lost",
        "payload": {"_anomaly_tag": "A1", "location_code": ATM_LOCATIONS[atm]},
        "correlation_id": corr_id,
        "message_id": str(uuid4()),
    })
    producer.send_event({
        "timestamp": (t + timedelta(seconds=random.randint(3, 8))).isoformat(), "source": "ATM_APP",
        "atm_id": atm, "event_type": "TIMEOUT", "severity": "ERROR",
        "message": "Request timed out",
        "payload": {"_anomaly_tag": "A1"},
        "correlation_id": corr_id,
        "message_id": str(uuid4()),
    })
    
    # Randomly include KAFKA signal (70% probability)
    if random.random() < 0.7:
        producer.send_event({
            "timestamp": (t + timedelta(seconds=random.randint(8, 15))).isoformat(), "source": "KAFKA",
            "atm_id": atm, "event_type": "STATUS", "severity": "INFO",
            "message": "ATM Offline",
            "payload": {"_anomaly_tag": "A1", "atm_status": "Offline"},
            "correlation_id": corr_id,
            "message_id": str(uuid4()),
        })
    
    # Randomly include TERMINAL_HANDLER signal (70% probability)
    if random.random() < 0.7:
        producer.send_event({
            "timestamp": (t + timedelta(seconds=random.randint(12, 20))).isoformat(), "source": "TERMINAL_HANDLER",
            "atm_id": atm, "event_type": "NETWORK_ERROR", "severity": "FATAL",
            "message": "Connection timed out",
            "payload": {"_anomaly_tag": "A1"},
            "correlation_id": corr_id,
            "message_id": str(uuid4()),
        })
    return atm


def inject_a2(producer, t: datetime) -> str | None:
    """Inject A2 Cash Cassette Empty.

    Fires a variable cascade (2-3 signals) across HARDWARE and KAFKA sharing a
    single correlation_id. The CASSETTE_EMPTY fires after CASSETTE_LOW with variable timing.
    Returns the ATM ID used.
    """
    atm = random.choice(ATMS)
    corr_id = str(uuid4())
    
    # Always include CASSETTE_LOW
    producer.send_event({
        "timestamp": t.isoformat(), "source": "HARDWARE", "atm_id": atm,
        "event_type": "CASSETTE_LOW", "severity": "WARNING",
        "message": "Cash low in cassette 1",
        "payload": {"_anomaly_tag": "A2"},
        "correlation_id": corr_id,
        "message_id": str(uuid4()),
    })
    
    # Variable delay for CASSETTE_EMPTY (3-8 minutes)
    empty_delay = random.randint(3, 8)
    producer.send_event({
        "timestamp": (t + timedelta(minutes=empty_delay)).isoformat(), "source": "HARDWARE",
        "atm_id": atm, "event_type": "CASSETTE_EMPTY", "severity": "CRITICAL",
        "message": "Cash empty in cassette 1",
        "payload": {"_anomaly_tag": "A2"},
        "correlation_id": corr_id,
        "message_id": str(uuid4()),
    })
    
    # Randomly include KAFKA OutOfService signal (80% probability)
    if random.random() < 0.8:
        kafka_delay = empty_delay + random.randint(2, 5)  # 2-5 minutes after cassette empty
        producer.send_event({
            "timestamp": (t + timedelta(minutes=kafka_delay)).isoformat(), "source": "KAFKA",
            "atm_id": atm, "event_type": "STATUS", "severity": "INFO",
            "message": "ATM Out of Service",
            "payload": {"_anomaly_tag": "A2", "atm_status": "OutOfService"},
            "correlation_id": corr_id,
            "message_id": str(uuid4()),
        })
    return atm


def inject_a3(producer, t: datetime) -> str | None:
    """Inject A3 JVM Memory Leak.

    State-based progressive emission — one message per call across 10 ticks.
    Produces monotonically rising JVM heap and GC pause metrics, terminating
    with a TERMINAL_HANDLER OOM_ERROR on the 10th call.
    Returns the ATM ID used.
    """
    atm_key = "a3"
    state = _get_progressive_state(atm_key)

    if state["produced"] >= 10:
        del _anomaly_state[atm_key]
        return state.get("atm")

    i = state["produced"]
    state["produced"] += 1
    tick_t = t + timedelta(seconds=i * 10)

    producer.send_metric({
        "timestamp": tick_t.isoformat(), "source": "PROMETHEUS",
        "entity_id": state["atm"], "metric_name": "jvm_memory_used_bytes",
        "metric_value": 1e8 + (i * 1e7),
        "payload": {"_anomaly_tag": "A3"},
        "correlation_id": state["corr_id"],
        "message_id": str(uuid4()),
    })
    gc_pause = min(5.0, i * 0.05)
    producer.send_metric({
        "timestamp": tick_t.isoformat(), "source": "PROMETHEUS",
        "entity_id": state["atm"], "metric_name": "jvm_gc_pause_seconds_sum",
        "metric_value": gc_pause,
        "payload": {"_anomaly_tag": "A3"},
        "correlation_id": state["corr_id"],
        "message_id": str(uuid4()),
    })
    cpu_usage = min(95.0, 20 + (i * 0.8))
    producer.send_metric({
        "timestamp": tick_t.isoformat(), "source": "CLOUD",
        "entity_id": state["atm"], "metric_name": "container/cpu/usage_time",
        "metric_value": cpu_usage,
        "payload": {"_anomaly_tag": "A3"},
        "correlation_id": state["corr_id"],
        "message_id": str(uuid4()),
    })

    if state["produced"] == 10:
        producer.send_event({
            "timestamp": tick_t.isoformat(), "source": "TERMINAL_HANDLER",
            "atm_id": state["atm"], "event_type": "OOM_ERROR", "severity": "FATAL",
            "message": "Java heap space",
            "payload": {"_anomaly_tag": "A3"},
            "correlation_id": state["corr_id"],
            "message_id": str(uuid4()),
        })
        del _anomaly_state[atm_key]
    return state.get("atm")


def inject_a4(producer, t: datetime) -> str | None:
    """Inject A4 Container Restart Loop.

    Fires a 3-message cascade: STARTUP → CRASH → STARTUP within 60 seconds,
    simulating a pod restart loop.
    Returns the ATM ID used.
    """
    atm = random.choice(ATMS)
    corr_id = str(uuid4())
    producer.send_event({
        "timestamp": t.isoformat(), "source": "TERMINAL_HANDLER", "atm_id": atm,
        "event_type": "STARTUP", "severity": "INFO",
        "message": "Pod starting",
        "payload": {"_anomaly_tag": "A4"},
        "correlation_id": corr_id,
        "message_id": str(uuid4()),
    })
    producer.send_event({
        "timestamp": (t + timedelta(seconds=30)).isoformat(), "source": "TERMINAL_HANDLER",
        "atm_id": atm, "event_type": "CRASH", "severity": "ERROR",
        "message": "Unexpected exit",
        "payload": {"_anomaly_tag": "A4"},
        "correlation_id": corr_id,
        "message_id": str(uuid4()),
    })
    producer.send_event({
        "timestamp": (t + timedelta(seconds=60)).isoformat(), "source": "TERMINAL_HANDLER",
        "atm_id": atm, "event_type": "STARTUP", "severity": "INFO",
        "message": "Pod restarting",
        "payload": {"_anomaly_tag": "A4"},
        "correlation_id": corr_id,
        "message_id": str(uuid4()),
    })
    # Add GCP metric for container restart count
    producer.send_metric({
        "timestamp": (t + timedelta(seconds=60)).isoformat(), "source": "CLOUD",
        "entity_id": atm, "metric_name": "container/restart_count",
        "metric_value": 2,
        "payload": {"_anomaly_tag": "A4"},
        "correlation_id": corr_id,
        "message_id": str(uuid4()),
    })
    return atm


def inject_a5(producer, t: datetime) -> str | None:
    """Inject A5 High Response Time Spike.

    Fires a variable cascade (8-12 messages) over 60-120 seconds with 
    progressively degrading success rate and variable response times > 3000ms.
    Includes ATM_APP TIMEOUT events for cross-source correlation.
    Returns the ATM ID used.
    """
    atm = random.choice(ATMS)
    corr_id = str(uuid4())
    
    # Variable number of messages (8-12) and duration (60-120 seconds)
    num_messages = random.randint(8, 12)
    duration = random.randint(60, 120)
    interval = duration / num_messages
    
    success_rate = 1.0
    for i in range(num_messages):
        tick_t = t + timedelta(seconds=i * interval)
        # Variable success rate drop (0.3 to 0.8)
        success_rate = max(0.3, success_rate - random.uniform(0.02, 0.12))
        # Variable response time threshold (3000-8000 ms)
        response_time = 3000 + random.randint(0, 5000)
        producer.send_event({
            "timestamp": tick_t.isoformat(), "source": "KAFKA", "atm_id": atm,
            "event_type": "METRIC", "severity": "INFO",
            "message": "Latency update",
            "payload": {
                "_anomaly_tag": "A5",
                "response_time_ms": response_time,
                "success_rate": round(success_rate, 3),
            },
            "correlation_id": corr_id,
            "message_id": str(uuid4()),
        })
        
        # Occasionally add ATM_APP TIMEOUT for cross-source correlation (40% probability)
        if random.random() < 0.4 and i > 0:
            producer.send_event({
                "timestamp": (tick_t + timedelta(seconds=random.randint(1, 5))).isoformat(), 
                "source": "ATM_APP", 
                "atm_id": atm,
                "event_type": "TIMEOUT", 
                "severity": "ERROR",
                "message": "Request timed out",
                "payload": {
                    "_anomaly_tag": "A5",
                    "error_code": "ERR-0012"
                },
                "correlation_id": corr_id,
                "message_id": str(uuid4()),
            })
    
    # Final status message
    producer.send_event({
        "timestamp": (t + timedelta(seconds=duration)).isoformat(), "source": "KAFKA",
        "atm_id": atm, "event_type": "STATUS", "severity": "WARNING",
        "message": "Success rate drop detected",
        "payload": {"_anomaly_tag": "A5", "success_rate": round(success_rate, 3)},
        "correlation_id": corr_id,
        "message_id": str(uuid4()),
    })
    return atm


def inject_a6(producer, t: datetime) -> str | None:
    """Inject A6 OS Memory Pressure.

    State-based progressive emission — one message per call across 120 ticks.
    Produces monotonically rising OS memory usage (20 → 90%), terminating
    with an ATM_APP TIMEOUT on the 120th call.
    Returns the ATM ID used.
    """
    atm_key = "a6"
    state = _get_progressive_state(atm_key)

    if state["produced"] >= 10:
        del _anomaly_state[atm_key]
        return state.get("atm")

    i = state["produced"]
    state["produced"] += 1
    tick_t = t + timedelta(seconds=i * 10)

    producer.send_metric({
        "timestamp": tick_t.isoformat(), "source": "OS",
        "entity_id": state["atm"], "metric_name": "memory_usage_percent",
        "metric_value": 20 + (i * 7),
        "payload": {"_anomaly_tag": "A6"},
        "correlation_id": state["corr_id"],
        "message_id": str(uuid4()),
    })

    if state["produced"] == 10:
        producer.send_event({
            "timestamp": tick_t.isoformat(), "source": "ATM_APP",
            "atm_id": state["atm"], "event_type": "TIMEOUT", "severity": "ERROR",
            "message": "OS resource timeout",
            "payload": {"_anomaly_tag": "A6", "error_code": "ERR-MEM"},
            "correlation_id": state["corr_id"],
            "message_id": str(uuid4()),
        })
        del _anomaly_state[atm_key]
    return state.get("atm")


def inject_a7(producer, t: datetime) -> str | None:
    """Inject A7 Out-of-Order Kafka Events.

    Fires a single malformed KAFKA event with offset=-1 and
    _anomaly_tag=A7_OUT_OF_ORDER.
    Returns the ATM ID used.
    """
    atm = random.choice(ATMS)
    producer.send_event({
        "timestamp": t.isoformat(), "source": "KAFKA", "atm_id": atm,
        "event_type": "METRIC", "severity": "INFO",
        "message": "Malformed event",
        "payload": {"_anomaly_tag": "A7_OUT_OF_ORDER", "offset": -1},
        "correlation_id": str(uuid4()),
        "message_id": str(uuid4()),
    })
    return atm


ANOMALY_REGISTRY = [
    ("A1", inject_a1, 300),
    ("A2", inject_a2, 600),
    ("A3", inject_a3, 10),
    ("A4", inject_a4, 300),
    ("A5", inject_a5, 300),
    ("A6", inject_a6, 10),
    ("A7", inject_a7, 300),
]
