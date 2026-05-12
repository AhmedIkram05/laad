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
        # Increased from maxconn=20 to 50 to handle concurrent loads from:
        # - Multiple API client requests (typically 4-8 concurrent)
        # - Generator (1 per second)
        # - ML detector (1 per 10 seconds)
        # - Background cleanup tasks
        _pool = psycopg2.pool.ThreadedConnectionPool(minconn=5, maxconn=50, **DB_CONFIG)
    return _pool


def get_conn() -> psycopg2.extensions.connection:
    """Check out a raw connection from the pool with retry logic.
    
    Implements exponential backoff to handle temporary pool exhaustion.
    
    Raises:
        psycopg2.pool.PoolError: If pool exhausted after retries.
    """
    import time
    pool = _get_pool()
    max_attempts = 3
    retry_delay = 0.1  # Start with 100ms
    
    for attempt in range(max_attempts):
        try:
            return pool.getconn()
        except psycopg2.pool.PoolError:
            if attempt < max_attempts - 1:
                # Exponential backoff: 0.1s, 0.2s before final attempt
                time.sleep(retry_delay)
                retry_delay *= 2
            else:
                # Final attempt failed, raise
                raise


def release_conn(conn: psycopg2.extensions.connection) -> None:
    # Ensure pooled connections are returned in a clean transaction state.
    try:
        conn.rollback()
    except Exception:
        # If rollback fails (e.g. bad/closed connection), still return it and
        # let the pool/client lifecycle handle replacement when needed.
        pass
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
