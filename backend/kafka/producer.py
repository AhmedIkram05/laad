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

log = logging.getLogger(__name__)

KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
TOPIC_EVENTS  = "atm-events"
TOPIC_METRICS = "atm-metrics"


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
        try:
            self._producer.send(TOPIC_EVENTS, value=msg)
        except KafkaError as exc:
            log.error("Failed to send event to %s: %s", TOPIC_EVENTS, exc)

    def send_metric(self, metric: dict) -> None:
        msg = self._add_message_id(metric)
        try:
            self._producer.send(TOPIC_METRICS, value=msg)
        except KafkaError as exc:
            log.error("Failed to send metric to %s: %s", TOPIC_METRICS, exc)

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