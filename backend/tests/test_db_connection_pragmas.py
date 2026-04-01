"""Tests for `get_db` PRAGMA settings and cross-thread usability.

Verifies that `get_db()` applies recommended PRAGMA settings for concurrent
writes (WAL journal mode, `foreign_keys = ON`, `busy_timeout`) and that the
returned connection is usable from another thread (i.e., created with
`check_same_thread=False`). The test uses `init_db` to create an isolated
SQLite file for assertions.
"""

import os
import sqlite3
import threading
import queue
from datetime import datetime, timezone

import backend.src.database.init_db as init_db_module
from backend.src.database.connection import get_db


def test_get_db_applies_pragmas_and_allows_cross_thread_write(tmp_path):
    tmp_db = tmp_path / "test_conn.db"
    schema_path = os.path.join(os.path.dirname(init_db_module.__file__), "schema.sql")

    assert init_db_module.init_db(db_path=str(tmp_db), schema_path=str(schema_path)) is True

    conn = get_db(str(tmp_db))

    try:
        # PRAGMA journal_mode returns the active journal mode
        jm = conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert str(jm).lower() == "wal"

        fk = conn.execute("PRAGMA foreign_keys").fetchone()[0]
        assert int(fk) == 1

        bt = conn.execute("PRAGMA busy_timeout").fetchone()[0]
        assert int(bt) >= 1000

        # Cross-thread write using the same connection (requires check_same_thread=False)
        q = queue.Queue()

        def thread_writer(c, q):
            try:
                c.execute("INSERT INTO events (timestamp, source, message, payload) VALUES (?, 'TEST', ?, '{}')", (datetime.now(timezone.utc).isoformat(), 't1'))
                c.commit()
                q.put(None)
            except Exception as e:
                q.put(e)

        t = threading.Thread(target=thread_writer, args=(conn, q))
        t.start()
        t.join(timeout=5)
        result = q.get_nowait()
        if result is not None:
            raise result

        # verify the write succeeded
        cur = sqlite3.connect(str(tmp_db))
        cur.row_factory = sqlite3.Row
        rows = cur.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        cur.close()
        assert rows >= 1

    finally:
        try:
            conn.close()
        except Exception:
            pass
