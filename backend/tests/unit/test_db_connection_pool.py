"""DB-free regression tests for the lazy connection pool initialiser."""

import threading
from unittest.mock import patch

import backend.src.database.connection as conn_mod
from backend.src.database.connection import _get_pool


def test_get_pool_concurrent_calls_share_one_pool():
    """Two threads racing _get_pool() must observe a single pool instance."""
    with (
        patch.object(conn_mod, "_pool", None),
        patch.object(conn_mod.psycopg2.pool, "ThreadedConnectionPool") as pool_cls,
    ):
        barrier = threading.Barrier(2)
        results = []

        def worker():
            barrier.wait()
            results.append(_get_pool())

        threads = [threading.Thread(target=worker) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert results[0] is results[1]
        assert pool_cls.call_count == 1
