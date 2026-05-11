"""Data retention cleanup module.

Deletes records older than the configured retention period using batched
deletes to avoid long WAL write-locks, then VACUUMs to reclaim disk space.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from backend.src.database.connection import get_conn, release_conn

logger = logging.getLogger(__name__)

BATCH_SIZE = 5000

TABLE_CONFIG = [
    ("events",           "timestamp", ""),
    ("metrics",          "timestamp", ""),
    ("ingestion_errors", "timestamp", ""),
    ("anomalies",        "detected_at", "AND is_active = 0"),
]


def batched_delete(conn, table: str, col: str, cutoff: str, extra_cond: str = "") -> int:
    """Deletes rows older than cutoff in batches of BATCH_SIZE.
    Commits between batches to yield the WAL write-lock to ingestion workers.
    """
    valid_tables = {t[0] for t in TABLE_CONFIG}
    if table not in valid_tables:
        raise ValueError(f"Invalid table for cleanup: {table}")

    total_deleted = 0
    while True:
        with conn.cursor() as cur:
            cur.execute(
                f"""DELETE FROM {table}
                    WHERE id IN (
                        SELECT id FROM {table}
                        WHERE {col} < %s
                        AND {col} IS NOT NULL
                        {extra_cond}
                        LIMIT %s
                    )""",
                (cutoff, BATCH_SIZE),
            )
            conn.commit()
            if cur.rowcount == 0:
                break
            total_deleted += cur.rowcount
    return total_deleted


def batched_delete_all(conn, table: str, extra_cond: str = "") -> int:
    """Delete rows from `table` in batches of BATCH_SIZE until empty.
    Returns total deleted.
    """
    valid_tables = {t[0] for t in TABLE_CONFIG}
    if table not in valid_tables:
        raise ValueError(f"Invalid table for cleanup: {table}")

    total_deleted = 0
    while True:
        with conn.cursor() as cur:
            cur.execute(
                f"""DELETE FROM {table}
                    WHERE id IN (
                        SELECT id FROM {table}
                        WHERE 1=1 {extra_cond}
                        LIMIT %s
                    )""",
                (BATCH_SIZE,),
            )
            conn.commit()
            if cur.rowcount == 0:
                break
            total_deleted += cur.rowcount
    return total_deleted


def run_wipe() -> dict:
    """Permanently delete all rows from configured cleanup tables.

    This runs batched deletes (to yield the WAL lock) and VACUUMs the DB.
    Intended to be called only by an admin and only when an operator explicitly
    requests a full data wipe.
    """
    conn = get_conn()
    deleted = {}

    try:
        for t_config in TABLE_CONFIG:
            table = t_config[0]
            extra_cond = t_config[2]
            count = batched_delete_all(conn, table, extra_cond)
            deleted[table] = count
            logger.info(f"  {table}: {count} rows deleted")

        # VACUUM: On PostgreSQL VACUUM requires suitable privileges and is
        # typically run by DBAs or scheduled maintenance. We skip automatic
        # VACUUM here to avoid permission errors in hosted environments.
        logger.info("Skipping VACUUM (for Postgres leave to DBA/maintenance)")

    finally:
        release_conn(conn)

    logger.info(f"Wipe complete: {deleted}")
    return {"action": "wipe", "deleted": deleted}


def run_cleanup() -> dict:
    """Main cleanup entry point. Opens the connection exactly once."""
    conn = get_conn()
    deleted = {}

    try:
        # Step 1: read retention config
        with conn.cursor() as cur:
            cur.execute("SELECT retention_days FROM retention_config WHERE id = 1")
            row = cur.fetchone()
            retention_days = row[0] if row else 7

        cutoff = (
            datetime.now(timezone.utc) - timedelta(days=retention_days)
        ).isoformat()
        logger.info(f"Cleanup started: cutoff={cutoff} ({retention_days}d retention)")

        # Step 2: batched deletes
        for t_config in TABLE_CONFIG:
            table = t_config[0]
            col = t_config[1]
            extra_cond = t_config[2]
            count = batched_delete(conn, table, col, cutoff, extra_cond)
            deleted[table] = count
            logger.info(f"  {table}: {count} rows deleted")

        # Step 3: VACUUM — must run outside any active transaction
        # VACUUM is skipped in automated cleanup (see run_wipe note)
    finally:
        release_conn(conn)

    logger.info(f"Cleanup complete: {deleted}")
    return {
        "cutoff": cutoff,
        "retention_days": retention_days,
        "deleted": deleted
    }