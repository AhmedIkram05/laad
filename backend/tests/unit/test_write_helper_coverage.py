"""Extra branches for backend.src.ingestion.write_helper.write_batch.

Existing test_write_helper_retry.py covers the main retry paths.
This file covers the generic-Exception branch, rollback-failure
swallowing, DatabaseError variants, and generator-row handling.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import psycopg2
import pytest

from backend.src.ingestion.write_helper import write_batch


def _conn():
    conn = MagicMock()
    cur = MagicMock()
    cur.mogrify.return_value = b"('x')"
    conn.cursor.return_value.__enter__.return_value = cur
    conn.cursor.return_value.__exit__.return_value = False
    cur.connection = conn
    conn.encoding = "UTF8"
    return conn, cur


class TestGenericException:
    def test_unexpected_error_rollbacks_and_raises(self):
        conn, cur = _conn()
        cur.execute.side_effect = ValueError("boom")
        # execute_values path calls cur.execute internally via mock;
        # force executemany path for determinism.
        with patch(
            "psycopg2.extras.execute_values", side_effect=ValueError("boom")
        ):
            with pytest.raises(ValueError, match="boom"):
                write_batch(conn, "INSERT INTO t (a) VALUES %s", [("x",)])
        assert conn.rollback.called

    def test_unexpected_error_rollback_failure_swallowed(self):
        conn, cur = _conn()
        conn.rollback.side_effect = RuntimeError("rollback gone")
        with patch(
            "psycopg2.extras.execute_values", side_effect=ValueError("boom")
        ):
            with pytest.raises(ValueError):
                write_batch(conn, "INSERT INTO t (a) VALUES %s", [("x",)])

    def test_executemany_unexpected_error(self):
        conn, cur = _conn()
        cur.executemany.side_effect = KeyError("k")
        with pytest.raises(KeyError):
            write_batch(conn, "UPDATE t SET a = %s", [("x",)])
        assert conn.rollback.called


class TestRollbackSwallowing:
    def test_transient_rollback_failure_still_retries(self):
        conn, cur = _conn()
        cur.execute.side_effect = [
            psycopg2.OperationalError("deadlock detected"),
            None,
        ]
        conn.rollback.side_effect = [RuntimeError("rb fail"), None]
        with patch("time.sleep", return_value=None):
            write_batch(conn, "INSERT INTO t (a) VALUES %s", [("x",)])
        assert conn.commit.called

    def test_non_transient_rollback_failure_swallowed(self):
        conn, cur = _conn()
        cur.execute.side_effect = psycopg2.OperationalError("permission denied")
        conn.rollback.side_effect = RuntimeError("rb fail")
        with pytest.raises(psycopg2.OperationalError):
            write_batch(conn, "INSERT INTO t (a) VALUES %s", [("x",)])


class TestDatabaseErrorVariants:
    def test_database_error_lock_transient_retries(self):
        conn, cur = _conn()
        cur.execute.side_effect = [
            psycopg2.DatabaseError("could not obtain lock on row"),
            None,
        ]
        with patch("time.sleep", return_value=None):
            write_batch(conn, "INSERT INTO t (a) VALUES %s", [("x",)])
        assert cur.execute.call_count == 2

    def test_database_error_cancel_transient(self):
        conn, cur = _conn()
        cur.execute.side_effect = [
            psycopg2.DatabaseError("canceling statement due to user request"),
            None,
        ]
        with patch("time.sleep", return_value=None):
            write_batch(conn, "INSERT INTO t (a) VALUES %s", [("x",)])

    def test_database_error_non_transient_no_retry(self):
        conn, cur = _conn()
        cur.execute.side_effect = psycopg2.DatabaseError("unique violation")
        with pytest.raises(psycopg2.DatabaseError):
            write_batch(conn, "INSERT INTO t (a) VALUES %s", [("x",)])
        assert cur.execute.call_count == 1

    def test_zero_retries_no_retry(self):
        conn, cur = _conn()
        cur.execute.side_effect = psycopg2.OperationalError("deadlock detected")
        with patch("time.sleep") as mock_sleep:
            with pytest.raises(psycopg2.OperationalError):
                write_batch(conn, "INSERT INTO t (a) VALUES %s", [("x",)], retries=0)
            mock_sleep.assert_not_called()


class TestSqlSelection:
    def test_lowercase_insert_uses_execute_values(self):
        conn, _ = _conn()
        with patch("psycopg2.extras.execute_values") as mock_ev:
            write_batch(conn, "insert into t (a) values %s", [("x",)])
            mock_ev.assert_called_once()

    def test_insert_without_placeholder_uses_executemany(self):
        conn, cur = _conn()
        with patch("psycopg2.extras.execute_values") as mock_ev:
            write_batch(conn, "INSERT INTO t (a) VALUES ('x')", [("x",)])
            mock_ev.assert_not_called()
            assert cur.executemany.called

    def test_rows_generator_consumed(self):
        conn, _ = _conn()

        def _gen():
            yield ("a",)
            yield ("b",)

        with patch("psycopg2.extras.execute_values") as mock_ev:
            write_batch(conn, "INSERT INTO t (a) VALUES %s", _gen())
            args, _ = mock_ev.call_args
            assert list(args[2]) == [("a",), ("b",)]

    def test_backoff_capped_at_max(self):
        conn, cur = _conn()
        cur.execute.side_effect = psycopg2.OperationalError("deadlock detected")
        seen = []
        with patch("time.sleep", side_effect=lambda s: seen.append(s)):
            with pytest.raises(psycopg2.OperationalError):
                write_batch(
                    conn,
                    "INSERT INTO t (a) VALUES %s",
                    [("x",)],
                    retries=3,
                    backoff_base=10.0,
                    backoff_max=2.0,
                )
        assert seen and all(s <= 2.0 for s in seen)
