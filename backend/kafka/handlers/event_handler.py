"""Handles atm-events Kafka messages.

Validates the message, writes to the events table, adds to the
ChromaDB buffer, and routes malformed messages to ingestion_errors.

Called by the consumer router for every message on atm-events topic.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

import psycopg2.extras

from backend.src.database.connection import get_cursor
from backend.kafka.chroma_buffer import ChromaBuffer, format_event_text
from backend.src.analytics.analytics_router import (
    increment_event_counter,
    track_unique_atm,
)

log = logging.getLogger(__name__)

REQUIRED_FIELDS = {"message_id", "timestamp", "source", "severity"}

# execute_values template (single %s replaced with the value rows) — used by
# the consumer to flush a whole poll batch in one INSERT + COMMIT.
EVENT_BATCH_INSERT_SQL = """
INSERT INTO events
    (timestamp, source, atm_id, correlation_id, transaction_id,
     event_type, severity, message, payload)
VALUES %s
"""


def handle_event(
    msg: dict, chroma_buffer: ChromaBuffer, row_buffer: "list[tuple] | None" = None
) -> bool:
    """Handle one atm-events message.

    When row_buffer is provided, the DB row is appended to it instead of being
    inserted immediately — the consumer flushes the whole poll batch in a
    single batched transaction (write_batch/execute_values). Post-DB side
    effects (Chroma buffer, analytics counters) run either way.
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
        msg.get("atm_id"),
        msg.get("correlation_id"),
        msg.get("transaction_id"),
        msg.get("event_type"),
        msg["severity"],
        msg.get("message"),
        psycopg2.extras.Json(msg.get("payload") or {}),
    )
    if row_buffer is not None:
        row_buffer.append(row)
    else:
        try:
            with get_cursor(commit=True) as cur:
                cur.execute(
                    """
                    INSERT INTO events
                        (timestamp, source, atm_id, correlation_id, transaction_id,
                         event_type, severity, message, payload)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    row,
                )
        except Exception as exc:
            log.error(
                "DB write failed for event (source=%s): %s", msg.get("source"), exc
            )
            return False

    atm_id = msg.get("atm_id")
    if atm_id:
        text = format_event_text(msg)
        ts_str = (
            msg["timestamp"] if isinstance(msg["timestamp"], str) else ts.isoformat()
        )
        severity = msg.get("severity")
        payload = msg.get("payload") or {}
        anomaly_tag = payload.get("_anomaly_tag") if isinstance(payload, dict) else None
        chroma_buffer.add_event(
            atm_id=atm_id,
            text=text,
            timestamp=ts_str,
            severity=severity,
            anomaly_tag=anomaly_tag,
        )
        track_unique_atm(atm_id)

    hour_bucket = ts.strftime("%Y-%m-%dT%H")
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
        log.warning("Routed malformed event to ingestion_errors: %s", error_detail)
    except Exception as exc:
        log.error("Failed to write ingestion_error: %s", exc)
