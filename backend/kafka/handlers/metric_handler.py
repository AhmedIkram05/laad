"""Handles atm-metrics Kafka messages.

Validates the message, writes to the metrics table, and routes
malformed messages to ingestion_errors.

Called by the consumer router for every message on atm-metrics topic.
Metrics are NOT embedded into ChromaDB — only event-type logs are.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

import psycopg2.extras

from backend.src.database.connection import get_cursor
from backend.src.analytics.analytics_router import (
    increment_event_counter,
    track_unique_atm,
)

log = logging.getLogger(__name__)

REQUIRED_FIELDS = {
    "message_id",
    "timestamp",
    "source",
    "entity_id",
    "metric_name",
    "metric_value",
}

# execute_values template (single %s replaced with the value rows) — used by
# the consumer to flush a whole poll batch in one INSERT + COMMIT.
METRIC_BATCH_INSERT_SQL = """
INSERT INTO metrics
    (timestamp, source, entity_id, metric_name, metric_value, payload)
VALUES %s
"""


def handle_metric(msg: dict, row_buffer: "list[tuple] | None" = None) -> bool:
    """Handle one atm-metrics message.

    When row_buffer is provided, the DB row is appended to it instead of being
    inserted immediately — the consumer flushes the whole poll batch in a
    single batched transaction (write_batch/execute_values).
    """
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

    row = (
        ts,
        msg["source"],
        msg["entity_id"],
        msg["metric_name"],
        metric_value,
        psycopg2.extras.Json(msg.get("payload") or {}),
    )
    if row_buffer is not None:
        row_buffer.append(row)
    else:
        try:
            with get_cursor(commit=True) as cur:
                cur.execute(
                    """
                    INSERT INTO metrics
                        (timestamp, source, entity_id, metric_name, metric_value, payload)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    row,
                )
        except Exception as exc:
            log.error(
                "DB write failed for metric (name=%s): %s", msg.get("metric_name"), exc
            )
            return False

    entity_id = msg.get("entity_id", "")
    if entity_id.startswith("ATM-"):
        track_unique_atm(entity_id)

    # Bucket by UTC hour — an offset-bearing producer timestamp must not
    # skew the analytics bucket toward its local offset.
    hour_bucket = ts.astimezone(timezone.utc).strftime("%Y-%m-%dT%H")
    increment_event_counter(msg["source"], hour_bucket)

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
