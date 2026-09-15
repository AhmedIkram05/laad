"""Kafka producer wrapper for the ATM log generator.

Provides a thread-safe singleton KafkaProducer that serialises messages
as UTF-8 JSON and sends to the correct topic based on message type.

Topics:
    atm-events   — event-type messages (ATM_APP, HARDWARE, TERMINAL_HANDLER, KAFKA)
    atm-metrics  — metric-type messages (PROMETHEUS, OS, CLOUD)

Usage:
    from backend.kafka.producer import get_producer
    producer = get_producer()
    producer.send_event({...})
    producer.send_metric({...})
"""

from __future__ import annotations

import json
import logging
import os
from uuid import uuid4
from datetime import datetime

from kafka import KafkaProducer
from kafka.errors import KafkaError
from opentelemetry import trace
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

log = logging.getLogger(__name__)

KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
TOPIC_EVENTS = "atm-events"
TOPIC_METRICS = "atm-metrics"

# Span names are contract (ADR-0002, plan §7) — stable, documented in docs/observability.md.
_PRODUCE_SPAN_NAMES = {
    TOPIC_EVENTS: "atm.events.produce",
    TOPIC_METRICS: "atm.metrics.produce",
}

_tracer = trace.get_tracer("laad.kafka")
_propagator = TraceContextTextMapPropagator()


def _serialise(data: dict) -> bytes:
    return json.dumps(data, default=str).encode("utf-8")


class ATMProducer:
    """Thread-safe Kafka producer wrapper."""

    def __init__(self):
        self._producer = KafkaProducer(
            bootstrap_servers=KAFKA_BOOTSTRAP,
            value_serializer=_serialise,
            acks="all",
            retries=5,
            retry_backoff_ms=200,
            linger_ms=10,
            compression_type="gzip",
        )
        log.info("KafkaProducer connected to %s", KAFKA_BOOTSTRAP)

    def _add_message_id(self, data: dict) -> dict:
        data = dict(data)
        data.setdefault("message_id", str(uuid4()))
        if isinstance(data.get("timestamp"), datetime):
            data["timestamp"] = data["timestamp"].isoformat()
        return data

    def send_event(self, event: dict) -> None:
        msg = self._add_message_id(event)
        self._send(TOPIC_EVENTS, msg)

    def send_metric(self, metric: dict) -> None:
        msg = self._add_message_id(metric)
        self._send(TOPIC_METRICS, msg)

    def _send(self, topic: str, msg: dict) -> None:
        """Produce one message wrapped in an own produce span, W3C-injected.

        Single choke point for send_event/send_metric, so generator code stays
        uninstrumented (plan §4.2). The traceparent is injected while the
        produce span is current, so the header advertises this span as the
        consumer's parent. kafka-python asserts (str, bytes) header tuples.
        Span attributes carry IDs only — no message bodies (plan §7).
        """
        attributes = {
            "topic": topic,
            "message_id": msg.get("message_id", ""),
            "atm_id": msg.get("atm_id") or msg.get("entity_id") or "",
        }
        try:
            with _tracer.start_as_current_span(
                _PRODUCE_SPAN_NAMES[topic], attributes=attributes
            ):
                headers: dict[str, str] = {}
                _propagator.inject(carrier=headers)
                self._producer.send(
                    topic,
                    value=msg,
                    headers=[(k, v.encode("utf-8")) for k, v in headers.items()],
                )
        except KafkaError as exc:
            log.error("Failed to send to %s: %s", topic, exc)

    def flush(self) -> None:
        self._producer.flush()

    def close(self) -> None:
        self._producer.flush()
        self._producer.close()
        log.info("KafkaProducer closed.")


_producer_instance = None


def get_producer() -> ATMProducer:
    global _producer_instance
    if _producer_instance is None:
        _producer_instance = ATMProducer()
    return _producer_instance
