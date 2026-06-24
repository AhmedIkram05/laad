"""Resilient write helper for Postgres batch writes.

Uses psycopg2's execute_values for efficient bulk inserts. Retries on
transient operational errors (deadlocks/serialization failures) with
exponential backoff.
"""

from __future__ import annotations

import time
import logging
from typing import Iterable

import psycopg2
import psycopg2.extras

logger = logging.getLogger(__name__)


def write_batch(
    conn: psycopg2.extensions.connection,
    sql: str,
    rows: Iterable[tuple],
    retries: int = 5,
    backoff_base: float = 0.1,
    backoff_max: float = 2.0,
) -> None:
    """Write a batch of rows using provided psycopg2 connection with retry/backoff.

    - `conn` must be a psycopg2 connection (obtained from database.connection.get_conn()).
    - `sql` is the parameterised insert SQL using %s placeholders.
    - `rows` is an iterable of parameter tuples.
    """
    attempt = 0
    rows = list(rows)
    # Attempt to use execute_values for best performance; requires the SQL to
    # end with a VALUES placeholder that execute_values can replace.
    while True:
        try:
            with conn.cursor() as cur:
                # psycopg2.extras.execute_values expects a template with a single %s
                # placeholder for the values. Example: "INSERT INTO t (a,b) VALUES %s"
                if "%s" in sql and sql.strip().upper().startswith("INSERT"):
                    psycopg2.extras.execute_values(cur, sql, rows, template=None)
                else:
                    cur.executemany(sql, rows)
            conn.commit()
            return
        except (psycopg2.OperationalError, psycopg2.DatabaseError) as e:
            msg = str(e).lower()
            transient = any(
                k in msg
                for k in (
                    "deadlock",
                    "could not serialize",
                    "could not obtain lock",
                    "canceling statement due to user request",
                    "lock",
                )
            )
            if transient and attempt < retries:
                try:
                    conn.rollback()
                except Exception:
                    pass
                wait = min(backoff_max, backoff_base * (2**attempt))
                logger.warning(
                    "Transient DB error during write; retrying in %.3fs (attempt %d): %s",
                    wait,
                    attempt + 1,
                    e,
                )
                time.sleep(wait)
                attempt += 1
                continue
            logger.exception("Write batch failed: %s", e)
            try:
                conn.rollback()
            except Exception:
                pass
            raise
        except Exception:
            logger.exception("Unexpected error during write_batch")
            try:
                conn.rollback()
            except Exception:
                pass
            raise
