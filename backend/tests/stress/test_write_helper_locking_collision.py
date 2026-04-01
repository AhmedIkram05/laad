"""Integration/stress test for `write_batch` under SQLite locking.

This test creates a real SQLite database (using the project's `init_db`) and
simulates a lock collision by opening an exclusive transaction on one
connection and holding it briefly while a second connection calls
`write_batch`. The goal is to validate that `write_batch` correctly retries
and eventually succeeds once the lock is released.
"""

import os
import sqlite3
import threading
import time
from datetime import datetime, timezone

import backend.src.database.init_db as init_db_module
from backend.src.ingestion.write_helper import write_batch


def _apply_pragmas(conn: sqlite3.Connection):
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("PRAGMA foreign_keys = ON")


def test_write_helper_handles_lock_collision(tmp_path):
    tmp_db = tmp_path / "test_lock_collision.db"
    schema_path = os.path.join(os.path.dirname(init_db_module.__file__), "schema.sql")

    # initialise schema
    assert init_db_module.init_db(db_path=str(tmp_db), schema_path=str(schema_path)) is True

    sql = "INSERT INTO events (timestamp, source, message, payload) VALUES (?, 'ATM_APP', ?, ?)"

    # Connection that acquires an exclusive lock and holds it briefly
    holder = sqlite3.connect(str(tmp_db), timeout=5.0, check_same_thread=False)
    _apply_pragmas(holder)

    now = datetime.now(timezone.utc).isoformat()
    # Acquire exclusive lock and insert without committing
    holder.execute("BEGIN EXCLUSIVE")
    holder.execute(sql, (now, "holder", "{}"))

    # Release the lock after a short delay in a background thread
    def release_lock():
        time.sleep(0.15)
        holder.commit()
        holder.close()

    releaser = threading.Thread(target=release_lock)
    releaser.start()

    # Writer connection will contend for the write; write_batch should retry and eventually succeed
    writer = sqlite3.connect(str(tmp_db), timeout=0.1, check_same_thread=False)
    _apply_pragmas(writer)

    try:
        write_batch(writer, sql, [(datetime.now(timezone.utc).isoformat(), "writer", "{}")], retries=20, backoff_base=0.01, backoff_max=0.05)
    finally:
        writer.close()

    releaser.join()

    # Verify both rows are present
    verifier = sqlite3.connect(str(tmp_db))
    _apply_pragmas(verifier)
    cnt = verifier.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    verifier.close()

    assert cnt >= 2
