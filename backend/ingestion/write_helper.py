"""Resilient write helper for SQLite batch writes.

Provides a single entrypoint `write_batch` which executes an executemany
within an explicit transaction and retries on transient `database is locked`
errors using exponential backoff.
"""
from __future__ import annotations

import sqlite3
import time
import logging
from typing import Iterable

logger = logging.getLogger(__name__)


def write_batch(conn: sqlite3.Connection, sql: str, rows: Iterable[tuple],
                retries: int = 5, backoff_base: float = 0.1, backoff_max: float = 2.0) -> None:
    """Write a batch of rows using provided connection with retry/backoff.

    - `conn` must be an sqlite3.Connection (obtained from database.connection.get_db()).
    - `sql` is the parameterised insert SQL.
    - `rows` is an iterable of parameter tuples.
    """
    attempt = 0
    rows = list(rows)
    while True:
        try:
            cur = conn.cursor()
            cur.execute('BEGIN')
            cur.executemany(sql, rows)
            conn.commit()
            return
        except sqlite3.OperationalError as e:
            if 'locked' in str(e).lower() and attempt < retries:
                wait = min(backoff_max, backoff_base * (2 ** attempt))
                logger.warning('Database locked during write; retrying in %.3fs (attempt %d)', wait, attempt + 1)
                time.sleep(wait)
                attempt += 1
                continue
            logger.exception('Write batch failed: %s', e)
            try:
                conn.rollback()
            except Exception:
                pass
            raise
        except Exception:
            logger.exception('Unexpected error during write_batch')
            try:
                conn.rollback()
            except Exception:
                pass
            raise
