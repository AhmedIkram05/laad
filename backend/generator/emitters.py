"""Baseline event emitters for continuous generation."""
from __future__ import annotations
import random
import logging
from datetime import datetime, timezone
from uuid import uuid4

from backend.generator.config import ATMS, ATM_LOCATIONS, POD_NAME, OS_VERSION

log = logging.getLogger(__name__)


def emit_atm_app_events(producer, t: datetime) -> None:
    """Emit ATM application activity events for a random subset of ATMs.

    Produces ACTIVITY events with INFO severity for ~35% of ATMs per tick.
    """
    for atm in ATMS:
        if random.random() < 0.35:
            producer.send_event({
                "timestamp": t.isoformat(),
                "source": "ATM_APP",
                "atm_id": atm,
                "event_type": "ACTIVITY",
                "severity": "INFO",
                "message": "User session active",
                "payload": {"location_code": ATM_LOCATIONS[atm]},
                "message_id": str(uuid4()),
            })


def emit_hardware_events(producer, t: datetime) -> None:
    """Emit hardware diagnostic events for a random subset of ATMs.

    Produces DIAGNOSTIC events with INFO severity for ~10% of ATMs per tick.
    """
    for atm in ATMS:
        if random.random() < 0.1:
            producer.send_event({
                "timestamp": t.isoformat(),
                "source": "HARDWARE",
                "atm_id": atm,
                "event_type": "DIAGNOSTIC",
                "severity": "INFO",
                "message": "Cash dispenser health check passed",
                "payload": {"component": "dispenser_v2"},
                "message_id": str(uuid4()),
            })


def emit_terminal_handler_events(producer, t: datetime) -> None:
    """Emit terminal handler log events for a random subset of ATMs.

    Produces LOG events with INFO severity for ~20% of ATMs per tick.
    """
    for atm in ATMS:
        if random.random() < 0.2:
            producer.send_event({
                "timestamp": t.isoformat(),
                "source": "TERMINAL_HANDLER",
                "atm_id": atm,
                "event_type": "LOG",
                "severity": "INFO",
                "message": "Handling request",
                "payload": {"pod": POD_NAME, "os": OS_VERSION},
                "message_id": str(uuid4()),
            })


def emit_kafka_events(producer, t: datetime) -> None:
    """Emit Kafka-sourced status events for all ATMs.

    Produces STATUS events with INFO severity for ~50% of ATMs per tick.
    """
    for atm in ATMS:
        if random.random() < 0.5:
            producer.send_event({
                "timestamp": t.isoformat(),
                "source": "KAFKA",
                "atm_id": atm,
                "event_type": "STATUS",
                "severity": "INFO",
                "message": "ATM status update",
                "payload": {"correlation_id": None},
                "message_id": str(uuid4()),
            })


def emit_kafka_metrics(producer, t: datetime) -> None:
    """Emit Kafka-sourced metric records for all ATMs.

    Produces throughput metrics for ~50% of ATMs per tick.
    """
    for atm in ATMS:
        if random.random() < 0.5:
            producer.send_metric({
                "timestamp": t.isoformat(),
                "source": "KAFKA",
                "entity_id": atm,
                "metric_name": "kafka_throughput",
                "metric_value": random.uniform(100, 500),
                "payload": {"correlation_id": None},
                "message_id": str(uuid4()),
            })


def emit_prometheus_metrics(producer, t: datetime) -> None:
    """Emit Prometheus JVM memory metrics for all ATMs.

    Produces jvm_memory_used_bytes for ~50% of ATMs per tick.
    """
    for atm in ATMS:
        if random.random() < 0.5:
            producer.send_metric({
                "timestamp": t.isoformat(),
                "source": "PROMETHEUS",
                "entity_id": atm,
                "metric_name": "jvm_memory_used_bytes",
                "metric_value": random.uniform(1e8, 5e8),
                "payload": {},
                "message_id": str(uuid4()),
            })


def emit_windows_os_metrics(producer, t: datetime) -> None:
    """Emit Windows OS snapshot metrics for all ATMs.

    Produces windows_os_snapshot for ~50% of ATMs per tick.
    """
    for atm in ATMS:
        if random.random() < 0.5:
            producer.send_metric({
                "timestamp": t.isoformat(),
                "source": "OS",
                "entity_id": atm,
                "metric_name": "windows_os_snapshot",
                "metric_value": random.uniform(10, 90),
                "payload": {},
                "message_id": str(uuid4()),
            })


def emit_gcp_metrics(producer, t: datetime) -> None:
    """Emit GCP container CPU metrics for all ATMs.

    Produces container/cpu/usage_time for ~50% of ATMs per tick.
    """
    for atm in ATMS:
        if random.random() < 0.5:
            producer.send_metric({
                "timestamp": t.isoformat(),
                "source": "CLOUD",
                "entity_id": atm,
                "metric_name": "container/cpu/usage_time",
                "metric_value": random.uniform(0.1, 1.0),
                "payload": {},
                "message_id": str(uuid4()),
            })


BASELINE_EMITTERS = [
    emit_atm_app_events,
    emit_hardware_events,
    emit_terminal_handler_events,
    emit_kafka_events,
    emit_kafka_metrics,
    emit_prometheus_metrics,
    emit_windows_os_metrics,
    emit_gcp_metrics,
]