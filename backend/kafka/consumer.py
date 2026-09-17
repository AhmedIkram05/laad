"""Kafka consumer service for the ATM platform.

Reads from two topics:
  - atm-events:   routes to event_handler -> PostgreSQL + ChromaDB
  - atm-metrics:  routes to metric_handler -> PostgreSQL

Deduplicates messages using an in-memory LRU set of message_ids.
Triggers anomaly detection after each batch (rate-limited to 30 seconds).
Routes malformed messages to ingestion_errors table.

The MLAnomalyDetector is cached at module level and reused across detection
cycles to avoid repeated model loading overhead.

Run as a standalone Docker service:
    python -m backend.kafka.consumer

Environment variables:
    KAFKA_BOOTSTRAP_SERVERS      Default: localhost:9092
    KAFKA_CONSUMER_GROUP         Default: atm-platform-consumer
    KAFKA_AUTO_OFFSET_RESET      Default: earliest
    KAFKA_POLL_TIMEOUT_MS        Default: 1000
    ANOMALY_TRIGGER_INTERVAL_S   Default: 30
    CHROMA_HOST                  Default: localhost
    CHROMA_PORT                  Default: 8000
    OLLAMA_BASE_URL              Default: http://localhost:11434
    CHROMA_WINDOW_SIZE           Default: 10
"""

from __future__ import annotations

import json
import logging
import os
import signal
import sys
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler

from kafka import KafkaConsumer
from backend.kafka.chroma_buffer import ChromaBuffer
from backend.kafka.deduplicator import Deduplicator
from backend.kafka.handlers import event_handler, metric_handler
from backend.kafka.handlers.event_handler import (
    _route_to_ingestion_errors as route_raw_ingestion_errors,
)
from backend.src.anomaly_detection.ml.ml_detector import MLAnomalyDetector
from backend.src.cache import get_redis_client
from backend.src.observability.tracing import setup_tracing
from opentelemetry import trace
from opentelemetry.context import Context
from opentelemetry.trace import Status, StatusCode
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [CONSUMER] %(message)s")

setup_tracing("atm-consumer")

_tracer = trace.get_tracer("laad.kafka")
_propagator = TraceContextTextMapPropagator()

KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
CONSUMER_GROUP = os.getenv("KAFKA_CONSUMER_GROUP", "atm-platform-consumer")
AUTO_OFFSET_RESET = os.getenv("KAFKA_AUTO_OFFSET_RESET", "earliest")
POLL_TIMEOUT_MS = int(os.getenv("KAFKA_POLL_TIMEOUT_MS", "1000"))
ANOMALY_INTERVAL_S = int(os.getenv("ANOMALY_TRIGGER_INTERVAL_S", "30"))

TOPIC_EVENTS = "atm-events"
TOPIC_METRICS = "atm-metrics"

_running = True
_cached_detector: "MLAnomalyDetector | None" = None


def _handle_sigterm(signum, frame):
    global _running
    log.info("SIGTERM received — shutting down consumer.")
    _running = False


def _deserialise(raw: bytes) -> dict | None:
    try:
        return json.loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        log.warning("Failed to deserialise message: %s", exc)
        return None


def _extract_parent(headers) -> Context:
    """Extract W3C context from raw Kafka header tuples for parent linkage.

    Header values arrive as bytes; decode defensively and tolerate either
    byte or str keys. Without a usable traceparent (e.g. messages produced
    before this rollout) the result is an invalid context and the consume
    span simply starts a fresh local trace.
    """
    carrier = {}
    for key, value in headers or []:
        key = key.decode("utf-8", "replace") if isinstance(key, bytes) else key
        value = value.decode("utf-8", "replace") if isinstance(value, bytes) else value
        if key and value is not None:
            carrier[str(key)] = value
    return _propagator.extract(carrier=carrier)


def _trigger_anomaly_detection() -> None:
    """Run the interval-guarded detection sweep inside an atm.detect stage span.

    Detection sweeps the DB window (not the individual message) and is gated
    by ANOMALY_TRIGGER_INTERVAL_S + the Redis lock, so this span is its own
    trace rather than a child of any consume span (plan §4.2). Attributes are
    real summary fields from the detector cycle — IDs and counts only.
    """
    global _cached_detector
    with _tracer.start_as_current_span("atm.detect") as span:
        try:
            from backend.src.anomaly_detection.ml.ml_detector import MLAnomalyDetector
            from backend.src.alerts.pubsub import publish_anomaly

            if _cached_detector is None:
                _cached_detector = MLAnomalyDetector()
            span.set_attribute(
                "laad.detect.models_loaded",
                bool(getattr(_cached_detector, "_loaded", False)),
            )
            n = _cached_detector.detect_and_save()
            span.set_attribute("laad.detect.anomalies_saved", n)
            if n:
                log.info("Anomaly detector: %d anomalies saved.", n)
                anomalies = _cached_detector._get_recent_anomalies(n)
                span.set_attribute(
                    "laad.detect.sources_fired",
                    ",".join(sorted({a.get("source", "?") for a in anomalies})),
                )
                span.set_attribute(
                    "laad.detect.anomaly_types",
                    ",".join(sorted({a.get("anomaly_type", "?") for a in anomalies})),
                )
                for anomaly in anomalies:
                    publish_anomaly(anomaly)
            sm = getattr(_cached_detector, "sm_crosscheck", None)
            if sm:
                span.set_attribute("laad.sm_crosscheck.ok", bool(sm.get("ok")))
                span.set_attribute("laad.sm_crosscheck.endpoint", sm["endpoint"])
                span.set_attribute("laad.sm_crosscheck.latency_ms", sm["latency_ms"])
        except Exception as exc:
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            log.warning("Anomaly detection failed: %s", exc)


_cached_syncer = None

LOCK_KEY = "lock:anomaly_detection"
LOCK_TIMEOUT_S = ANOMALY_INTERVAL_S - 5


def _acquire_detection_lock() -> bool:
    """Attempt to acquire a distributed lock via Redis SET NX EX.

    Returns True if lock acquired, False if already held by another consumer.
    Falls back to True (proceed) when Redis is unavailable.
    """
    client = get_redis_client()
    if client is None:
        log.debug("Redis unavailable — skipping distributed lock for anomaly detection")
        return True

    try:
        acquired = client.set(LOCK_KEY, "1", nx=True, ex=LOCK_TIMEOUT_S)
        if acquired:
            log.debug("Acquired anomaly detection lock")
        else:
            log.debug("Anomaly detection lock held by another consumer — skipping")
        return bool(acquired)
    except Exception as e:
        log.warning(f"Redis lock acquisition failed, proceeding without lock: {e}")
        return True


def _release_detection_lock() -> None:
    """Release the distributed detection lock."""
    client = get_redis_client()
    if client is None:
        return
    try:
        client.delete(LOCK_KEY)
        log.debug("Released anomaly detection lock")
    except Exception as e:
        log.warning(f"Failed to release detection lock: {e}")


def _trigger_anomaly_sync() -> None:
    """Sync UNKNOWN/NORMAL anomalies from DB to ChromaDB (own stage span)."""
    global _cached_syncer
    with _tracer.start_as_current_span("atm.anomaly.sync") as span:
        try:
            from backend.kafka.anomaly_syncer import AnomalySyncer

            if _cached_syncer is None:
                _cached_syncer = AnomalySyncer()
            result = _cached_syncer.sync_once()
            span.set_attribute("laad.sync.synced", result.get("synced", 0))
            span.set_attribute("laad.sync.status", result.get("status", "unknown"))
            if result.get("synced", 0) > 0:
                log.info(
                    "Anomaly syncer: %d anomalies synced to ChromaDB", result["synced"]
                )
        except Exception as exc:
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            log.warning("Anomaly sync failed: %s", exc)


def _start_health_server() -> None:
    """Start a lightweight HTTP health server on port 8081 for ECS target group checks.

    Serves {"status": "ok"} on GET /health. Runs as daemon thread.
    """

    class _HealthHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path == "/health":
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"status":"ok"}')
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, fmt, *args) -> None:
            log.debug("Health server: %s", fmt % args)

    try:
        server = HTTPServer(
            ("0.0.0.0", int(os.getenv("KAFKA_HEALTH_PORT", "8081"))), _HealthHandler
        )
        log.info("Health server listening on 0.0.0.0:%d", server.server_port)
        server.serve_forever()
    except OSError as exc:
        log.warning("Health server failed to start: %s", exc)


def run_consumer() -> None:
    signal.signal(signal.SIGTERM, _handle_sigterm)
    signal.signal(signal.SIGINT, _handle_sigterm)

    # Start ECS health check server on a daemon thread
    health_thread = threading.Thread(target=_start_health_server, daemon=True)
    health_thread.start()
    log.info("Health server thread started")

    dedup = Deduplicator(max_size=10_000)
    chroma = ChromaBuffer()

    # Kafka connection with retry — up to 5 attempts, 10-second delay
    consumer = None
    for attempt in range(1, 6):
        try:
            consumer = KafkaConsumer(
                TOPIC_EVENTS,
                TOPIC_METRICS,
                bootstrap_servers=KAFKA_BOOTSTRAP,
                group_id=CONSUMER_GROUP,
                auto_offset_reset=AUTO_OFFSET_RESET,
                enable_auto_commit=False,
                value_deserializer=lambda raw: raw,
                max_poll_records=500,
                session_timeout_ms=30_000,
                heartbeat_interval_ms=10_000,
                fetch_min_bytes=1,
                max_partition_fetch_bytes=10485760,
            )
            log.info(
                "Kafka consumer connected (attempt %d/5). Bootstrap: %s",
                attempt,
                KAFKA_BOOTSTRAP,
            )
            break
        except Exception as e:
            log.error("Kafka connection failed (attempt %d/5): %s", attempt, e)
            if attempt < 5:
                time.sleep(10)
            else:
                log.critical("All 5 Kafka connection attempts failed — exiting")
                sys.exit(1)

    log.info(
        "Consumer started. Topics: %s, %s. Group: %s",
        TOPIC_EVENTS,
        TOPIC_METRICS,
        CONSUMER_GROUP,
    )

    last_anomaly_trigger = 0.0
    processed = 0
    errors = 0

    try:
        while _running:
            records = consumer.poll(timeout_ms=POLL_TIMEOUT_MS)

            for topic_partition, messages in records.items():
                topic = topic_partition.topic

                for raw_msg in messages:
                    msg = _deserialise(raw_msg.value)

                    if msg is None:
                        route_raw_ingestion_errors(
                            source="KAFKA_CONSUMER",
                            error_detail="Failed to deserialise message bytes",
                            raw_input=repr(raw_msg.value[:500]),
                        )
                        errors += 1
                        continue

                    message_id = msg.get("message_id", "")
                    if message_id and dedup.is_duplicate(message_id) is True:
                        log.debug("Duplicate message_id=%s — skipping.", message_id)
                        continue
                    if message_id:
                        dedup.mark_seen(message_id)

                    # Consume span joins the producer's trace via the injected
                    # traceparent; attrs are IDs/locations only — never bodies.
                    with _tracer.start_as_current_span(
                        "atm.event.consume",
                        context=_extract_parent(raw_msg.headers),
                        attributes={
                            "topic": topic,
                            "partition": raw_msg.partition,
                            "offset": raw_msg.offset,
                            "message_id": message_id,
                        },
                    ):
                        if topic == TOPIC_EVENTS:
                            ok = event_handler.handle_event(msg, chroma)
                        elif topic == TOPIC_METRICS:
                            ok = metric_handler.handle_metric(msg)
                        else:
                            log.warning("Unknown topic: %s", topic)
                            ok = False

                    if ok:
                        processed += 1
                    else:
                        errors += 1

            if records:
                consumer.commit()

            now = time.monotonic()
            if processed > 0 and (now - last_anomaly_trigger) >= ANOMALY_INTERVAL_S:
                if _acquire_detection_lock():
                    try:
                        log.info(
                            "Triggering anomaly detection (processed=%d, last_trigger=%.1fs ago)",
                            processed,
                            now - last_anomaly_trigger,
                        )
                        _trigger_anomaly_detection()
                        _trigger_anomaly_sync()
                    finally:
                        _release_detection_lock()
                    last_anomaly_trigger = now
                else:
                    log.debug(
                        "Skipping anomaly detection — another consumer holds the lock"
                    )

            if processed % 500 == 0 and processed > 0:
                log.info("Processed %d messages (%d errors).", processed, errors)

    except KeyboardInterrupt:
        log.info("KeyboardInterrupt — shutting down consumer.")
    finally:
        log.info("Flushing ChromaDB buffer before shutdown...")
        chroma.flush_all()
        consumer.close()
        log.info(
            "Consumer shut down. Total processed: %d, errors: %d", processed, errors
        )


if __name__ == "__main__":
    run_consumer()
