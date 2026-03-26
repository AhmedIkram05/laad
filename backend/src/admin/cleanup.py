"""Data retention cleanup module.

Deletes records older than the configured retention period using batched
deletes to avoid long WAL write-locks, then VACUUMs to reclaim disk space.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from backend.src.database.connection import get_db

logger = logging.getLogger(__name__)

BATCH_SIZE = 5000

TABLE_CONFIG = [
    ("events",           "timestamp"),
    ("metrics",          "timestamp"),
    ("anomalies",        "detected_at"),
    ("ingestion_errors", "timestamp"),
    ("otp_tokens",       "created_at"),  # created_at ensures unused expired tokens are also purged
]


def batched_delete(conn, table: str, col: str, cutoff: str) -> int:
    """Deletes rows older than cutoff in batches of BATCH_SIZE.
    Commits between batches to yield the WAL write-lock to ingestion workers.
    """
    if (table, col) not in TABLE_CONFIG:
        raise ValueError(f"Invalid table/column for cleanup: {table}.{col}")

    total_deleted = 0
    while True:
        cursor = conn.execute(
            f"""DELETE FROM {table}
                WHERE id IN (
                    SELECT id FROM {table}
                    WHERE {col} < ?
                    AND {col} IS NOT NULL
                    LIMIT ?
                )""",
            (cutoff, BATCH_SIZE)
        )
        conn.commit()
        if cursor.rowcount == 0:
            break
        total_deleted += cursor.rowcount
    return total_deleted


def run_cleanup() -> dict:
    """Main cleanup entry point. Opens the connection exactly once."""
    conn = get_db()
    deleted = {}

    try:
        # Step 1: read retention config
        row = conn.execute(
            "SELECT retention_days FROM retention_config WHERE id = 1"
        ).fetchone()
        retention_days = row["retention_days"] if row else 30

        cutoff = (
            datetime.now(timezone.utc) - timedelta(days=retention_days)
        ).isoformat()
        logger.info(f"Cleanup started: cutoff={cutoff} ({retention_days}d retention)")

        # Step 2: batched deletes
        for table, col in TABLE_CONFIG:
            count = batched_delete(conn, table, col, cutoff)
            deleted[table] = count
            logger.info(f"  {table}: {count} rows deleted")

        # Step 3: VACUUM — must run outside any active transaction
        conn.commit()               # ensure no implicit transaction is open
        conn.isolation_level = None # switch to autocommit mode
        conn.execute("VACUUM")
        logger.info("VACUUM complete")

    finally:
        conn.isolation_level = ""   # reset to default
        conn.close()                # close exactly once

    logger.info(f"Cleanup complete: {deleted}")
    return {
        "cutoff": cutoff,
        "retention_days": retention_days,
        "deleted": deleted
    }