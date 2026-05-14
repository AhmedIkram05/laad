"""Handles atm-metrics Kafka messages.

Validates the message, writes to the metrics table, and routes
malformed messages to ingestion_errors.

Called by the consumer router for every message on atm-metrics topic.
Metrics are NOT embedded into ChromaDB — only event-type logs are.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import psycopg2.extras

from backend.src.database.connection import get_cursor

log = logging.getLogger(__name__)

REQUIRED_FIELDS = {"message_id", "timestamp", "source", "entity_id", "metric_name", "metric_value"}


def handle_metric(msg: dict) -> bool:
    missing = REQUIRED_FIELDS - set(msg.keys())
    if missing:
        _route_to_ingestion_errors(
            source=msg.get("source", "UNKNOWN"),
            error_detail=f"Missing required fields: {missing}",
            raw_input=json.dumps(msg),
        )
        return False

    try:
        metric_value = float(msg["metric_value"])
    except (TypeError, ValueError) as exc:
        _route_to_ingestion_errors(
            source=msg.get("source", "UNKNOWN"),
            error_detail=f"metric_value not numeric: {msg.get('metric_value')!r} — {exc}",
            raw_input=json.dumps(msg),
        )
        return False

    try:
        ts = msg["timestamp"]
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError) as exc:
        _route_to_ingestion_errors(
            source=msg.get("source", "UNKNOWN"),
            error_detail=f"Invalid timestamp: {exc}",
            raw_input=json.dumps(msg),
        )
        return False

    try:
        with get_cursor(commit=True) as cur:
            cur.execute(
                """
                INSERT INTO metrics
                    (timestamp, source, entity_id, metric_name, metric_value, payload)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    ts,
                    msg["source"],
                    msg["entity_id"],
                    msg["metric_name"],
                    metric_value,
                    psycopg2.extras.Json(msg.get("payload") or {}),
                ),
            )
    except Exception as exc:
        log.error("DB write failed for metric (name=%s): %s", msg.get("metric_name"), exc)
        return False

    return True


def _route_to_ingestion_errors(source: str, error_detail: str, raw_input: str) -> None:
    try:
        with get_cursor(commit=True) as cur:
            cur.execute(
                """
                INSERT INTO ingestion_errors (timestamp, source, error_detail, raw_input)
                VALUES (NOW(), %s, %s, %s)
                """,
                (source, error_detail, raw_input),
            )
        log.warning("Routed malformed metric to ingestion_errors: %s", error_detail)
    except Exception as exc:
        log.error("Failed to write ingestion_error: %s", exc)