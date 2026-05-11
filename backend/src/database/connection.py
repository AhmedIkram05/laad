from __future__ import annotations

import psycopg2
import psycopg2.pool
import psycopg2.extras
from contextlib import contextmanager
from typing import Optional

from backend.src.database.config import DB_CONFIG

# Thread-safe connection pool (lazy initialisation)
_pool: Optional[psycopg2.pool.ThreadedConnectionPool] = None


def _get_pool() -> psycopg2.pool.ThreadedConnectionPool:
    global _pool
    if _pool is None:
        _pool = psycopg2.pool.ThreadedConnectionPool(minconn=2, maxconn=10, **DB_CONFIG)
    return _pool


def get_conn() -> psycopg2.extensions.connection:
    """Check out a raw connection from the pool. Caller must return it with release_conn()."""
    return _get_pool().getconn()


def release_conn(conn: psycopg2.extensions.connection) -> None:
    _get_pool().putconn(conn)


@contextmanager
def get_cursor(commit: bool = False):
    """Context manager yielding a RealDictCursor.

    Yields a cursor that returns rows as dicts. If `commit` is True the
    connection will be committed after the block; exceptions will rollback.
    """
    conn = get_conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            yield cur
            if commit:
                conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        release_conn(conn)
