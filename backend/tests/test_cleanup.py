import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from backend.src.admin import cleanup as cleanup_mod
from backend.database import init_db as init_db_module


def _apply_pragmas(conn: sqlite3.Connection):
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("PRAGMA foreign_keys = ON")


def _make_ts(days_delta: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days_delta)).isoformat()


def _insert_sample_rows(db_path: str, retention_days: int = 1, old_count: int = 3, new_count: int = 2):
    conn = sqlite3.connect(db_path)
    _apply_pragmas(conn)
    cur = conn.cursor()

    now = datetime.now(timezone.utc)
    old_ts = (now - timedelta(days=retention_days + 1)).isoformat()
    new_ts = now.isoformat()

    # events
    for i in range(old_count):
        cur.execute(
            "INSERT INTO events (timestamp, source, message, payload) VALUES (?, 'ATM_APP', ?, ?)",
            (old_ts, f"old event {i}", '{}')
        )
    for i in range(new_count):
        cur.execute(
            "INSERT INTO events (timestamp, source, message, payload) VALUES (?, 'ATM_APP', ?, ?)",
            (new_ts, f"new event {i}", '{}')
        )

    # metrics
    for i in range(old_count):
        cur.execute(
            "INSERT INTO metrics (timestamp, source, entity_id, metric_name, metric_value, payload) VALUES (?, 'OS', 'ATM-GB-0001', 'cpu', 1.0, '{}')",
            (old_ts,)
        )
    for i in range(new_count):
        cur.execute(
            "INSERT INTO metrics (timestamp, source, entity_id, metric_name, metric_value, payload) VALUES (?, 'OS', 'ATM-GB-0001', 'cpu', 1.0, '{}')",
            (new_ts,)
        )

    # anomalies
    for i in range(old_count):
        cur.execute(
            "INSERT INTO anomalies (detected_at, anomaly_type, severity, title, explanation) VALUES (?, 'A1', 'HIGH', ?, ?)",
            (old_ts, f"old anomaly {i}", "ex")
        )
    for i in range(new_count):
        cur.execute(
            "INSERT INTO anomalies (detected_at, anomaly_type, severity, title, explanation) VALUES (?, 'A1', 'HIGH', ?, ?)",
            (new_ts, f"new anomaly {i}", "ex")
        )

    # ingestion_errors
    for i in range(old_count):
        cur.execute(
            "INSERT INTO ingestion_errors (timestamp, source, error_detail) VALUES (?, 'INGEST', ?)",
            (old_ts, f"err {i}")
        )
    for i in range(new_count):
        cur.execute(
            "INSERT INTO ingestion_errors (timestamp, source, error_detail) VALUES (?, 'INGEST', ?)",
            (new_ts, f"err new {i}")
        )

    # otp_tokens
    for i in range(old_count):
        cur.execute(
            "INSERT INTO otp_tokens (token, role, created_at, expires_at) VALUES (?, 'user', ?, ?)",
            (f"told{i}", old_ts, (now + timedelta(days=1)).isoformat())
        )
    for i in range(new_count):
        cur.execute(
            "INSERT INTO otp_tokens (token, role, created_at, expires_at) VALUES (?, 'user', ?, ?)",
            (f"tnew{i}", new_ts, (now + timedelta(days=1)).isoformat())
        )

    conn.commit()
    conn.close()


@pytest.mark.parametrize("retention_days", [1])
def test_run_cleanup_deletes_old_rows(tmp_path, monkeypatch, retention_days):
    db_file = tmp_path / "test_cleanup.db"
    # initialize schema + seeds
    init_db_module.init_db(db_path=str(db_file))

    # set retention_days to small value so our old rows are eligible
    conn = sqlite3.connect(str(db_file))
    _apply_pragmas(conn)
    cur = conn.cursor()
    cur.execute("UPDATE retention_config SET retention_days = ? WHERE id = 1", (retention_days,))
    conn.commit()
    conn.close()

    # insert sample rows: old and new
    _insert_sample_rows(str(db_file), retention_days=retention_days, old_count=3, new_count=2)

    # monkeypatch cleanup.get_db to open connections to our test DB
    def _test_get_db():
        c = sqlite3.connect(str(db_file))
        _apply_pragmas(c)
        return c

    monkeypatch.setattr(cleanup_mod, "get_db", _test_get_db)

    result = cleanup_mod.runCleanup()

    assert result["retention_days"] == retention_days
    # verify per-table deleted counts are >= 1 for our old inserts
    for table, _col in cleanup_mod.TABLE_CONFIG:
        assert table in result["deleted"]
        assert result["deleted"][table] >= 1

    # verify DB now contains only the new rows for a sample table
    conn2 = sqlite3.connect(str(db_file))
    _apply_pragmas(conn2)
    cur2 = conn2.cursor()
    rows = cur2.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    assert rows == 2
    conn2.close()


def test_run_cleanup_defaults_to_30_when_no_config(tmp_path, monkeypatch):
    db_file = tmp_path / "test_cleanup2.db"
    init_db_module.init_db(db_path=str(db_file))

    # remove retention row to force default path
    conn = sqlite3.connect(str(db_file))
    _apply_pragmas(conn)
    conn.execute("DELETE FROM retention_config WHERE id = 1")
    conn.commit()
    conn.close()

    # insert an old row older than 31 days
    conn2 = sqlite3.connect(str(db_file))
    _apply_pragmas(conn2)
    old_ts = (datetime.now(timezone.utc) - timedelta(days=31)).isoformat()
    conn2.execute("INSERT INTO events (timestamp, source, message, payload) VALUES (?, 'ATM_APP', 'old', '{}')", (old_ts,))
    conn2.commit()
    conn2.close()

    def _test_get_db3():
        c = sqlite3.connect(str(db_file))
        _apply_pragmas(c)
        return c

    monkeypatch.setattr(cleanup_mod, "get_db", _test_get_db3)

    result = cleanup_mod.runCleanup()
    assert result["retention_days"] == 30


def test_batched_delete_commits_between_batches(tmp_path, monkeypatch):
    db_file = tmp_path / "test_cleanup3.db"
    init_db_module.init_db(db_path=str(db_file))

    # set retention to 1 day and insert many old rows into events
    conn = sqlite3.connect(str(db_file))
    _apply_pragmas(conn)
    conn.execute("UPDATE retention_config SET retention_days = 1 WHERE id = 1")
    conn.commit()

    old_ts = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    total_rows = 7
    for i in range(total_rows):
        conn.execute("INSERT INTO events (timestamp, source, message, payload) VALUES (?, 'ATM_APP', ?, '{}')", (old_ts, f"old {i}"))
    conn.commit()
    conn.close()

    # reduce BATCH_SIZE for test speed
    monkeypatch.setattr(cleanup_mod, "BATCH_SIZE", 2)
    def _test_get_db2():
        c = sqlite3.connect(str(db_file))
        _apply_pragmas(c)
        return c

    monkeypatch.setattr(cleanup_mod, "get_db", _test_get_db2)

    result = cleanup_mod.runCleanup()
    assert result["deleted"]["events"] == total_rows
