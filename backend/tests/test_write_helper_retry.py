"""Unit tests for `write_helper.write_batch`.

These unit tests simulate SQLite behavior to verify the retry and backoff
logic in `write_batch` when `sqlite3.OperationalError('database is locked')`
is raised. The tests use a dummy connection/cursor and monkeypatch
`time.sleep` to avoid real delays.

Focus:
- `test_write_batch_retries_and_succeeds`: ensures write_batch retries on
    transient locked errors, rolls back between attempts, and commits when
    successful.
- `test_write_batch_exhausts_retries_and_raises`: ensures write_batch raises
    after exhausting the configured retries.
"""

import sqlite3
import pytest

from backend.src.ingestion.write_helper import write_batch


class _DummyCursor:
    def __init__(self, conn):
        self._conn = conn

    def execute(self, sql, params=None):
        # BEGIN is expected by write_batch
        if isinstance(sql, str) and sql.strip().upper().startswith("BEGIN"):
            self._conn.begin_calls += 1
            return None
        return None

    def executemany(self, sql, rows):
        self._conn.executemany_calls += 1
        if self._conn.failures_before_success > 0:
            self._conn.failures_before_success -= 1
            raise sqlite3.OperationalError("database is locked")
        # record executed rows for assertion
        self._conn.executed_rows = list(rows)
        return None


class _DummyConn:
    def __init__(self, failures_before_success: int = 0):
        self.failures_before_success = failures_before_success
        self.executemany_calls = 0
        self.begin_calls = 0
        self.executed_rows = None
        self.committed = False
        self.rollback_calls = 0

    def cursor(self):
        return _DummyCursor(self)

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rollback_calls += 1


def test_write_batch_retries_and_succeeds(monkeypatch):
    # Arrange: dummy connection will fail twice then succeed
    dummy = _DummyConn(failures_before_success=2)

    # Avoid sleeping during tests
    monkeypatch.setattr('backend.src.ingestion.write_helper.time.sleep', lambda _s: None)

    # Act
    write_batch(dummy, "INSERT INTO foo (a) VALUES (?)", [(1,), (2,)], retries=5, backoff_base=0.01, backoff_max=0.1)

    # Assert: succeeded and committed, and attempted executemany 3 times (2 failures + 1 success)
    assert dummy.committed is True
    assert dummy.executed_rows == [(1,), (2,)]
    assert dummy.executemany_calls == 3
    assert dummy.rollback_calls >= 2


def test_write_batch_exhausts_retries_and_raises(monkeypatch):
    dummy = _DummyConn(failures_before_success=5)
    monkeypatch.setattr('backend.src.ingestion.write_helper.time.sleep', lambda _s: None)

    with pytest.raises(sqlite3.OperationalError):
        write_batch(dummy, "INSERT INTO foo (a) VALUES (?)", [(1,)], retries=2, backoff_base=0.01, backoff_max=0.05)
