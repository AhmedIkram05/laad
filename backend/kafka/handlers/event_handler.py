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

log = logging.getLogger(__name__)

REQUIRED_FIELDS = {"message_id", "timestamp", "source", "severity"}


def handle_event(msg: dict, chroma_buffer: ChromaBuffer) -> bool:
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

    try:
        with get_cursor(commit=True) as cur:
            cur.execute(
                """
                INSERT INTO events
                    (timestamp, source, atm_id, correlation_id, transaction_id,
                     event_type, severity, message, payload)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    ts,
                    msg["source"],
                    msg.get("atm_id"),
                    msg.get("correlation_id"),
                    msg.get("transaction_id"),
                    msg.get("event_type"),
                    msg["severity"],
                    msg.get("message"),
                    psycopg2.extras.Json(msg.get("payload") or {}),
                ),
            )
    except Exception as exc:
        log.error("DB write failed for event (source=%s): %s", msg.get("source"), exc)
        return False

    atm_id = msg.get("atm_id")
    if atm_id:
        text = format_event_text(msg)
        ts_str = msg["timestamp"] if isinstance(msg["timestamp"], str) else ts.isoformat()
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