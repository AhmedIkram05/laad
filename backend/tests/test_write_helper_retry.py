"""Tests for write_helper batch writing with retry/backoff.

Verifies execute_values vs executemany selection,
transient error retry logic, exponential backoff,
and non-transient error propagation.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import psycopg2
import pytest

from backend.src.ingestion.write_helper import write_batch


@pytest.fixture
def mock_conn():
    conn = MagicMock(spec=psycopg2.extensions.connection)
    cursor = MagicMock()
    conn.cursor.return_value = cursor
    conn.cursor.return_value.__enter__.return_value = cursor
    return conn


class TestWriteBatch:
    def test_uses_execute_values_for_insert(self, mock_conn):
        """INSERT with %s placeholder triggers execute_values."""
        sql = "INSERT INTO events (source, message) VALUES %s"
        rows = [("ATM_APP", "test")]

        with patch("psycopg2.extras.execute_values") as mock_ev:
            write_batch(mock_conn, sql, rows)

        mock_ev.assert_called_once()
        assert mock_conn.commit.called

    def test_uses_executemany_for_non_insert(self, mock_conn):
        """Non-INSERT SQL uses executemany."""
        sql = "UPDATE events SET message = %s WHERE id = %s"
        rows = [("updated", 1)]

        with patch("psycopg2.extras.execute_values") as mock_ev:
            write_batch(mock_conn, sql, rows)

        mock_ev.assert_not_called()
        assert mock_conn.cursor.return_value.__enter__.return_value.executemany.called

    def test_retries_on_transient_deadlock(self, mock_conn):
        """Transient OperationalError (deadlock) triggers retry."""
        cursor = mock_conn.cursor.return_value.__enter__.return_value
        cursor.execute.side_effect = [
            psycopg2.OperationalError("deadlock detected"),
            None,
        ]

        write_batch(mock_conn, "INSERT INTO t (a) VALUES %s", [("x",)])

        # retry happened
        assert cursor.execute.call_count == 2
        assert mock_conn.rollback.called
        assert mock_conn.commit.called

    def test_raises_after_max_retries(self, mock_conn):
        """After max retries exhausted, exception is re-raised."""
        cursor = mock_conn.cursor.return_value.__enter__.return_value
        cursor.execute.side_effect = psycopg2.OperationalError("deadlock detected")

        with pytest.raises(psycopg2.OperationalError):
            write_batch(mock_conn, "INSERT INTO t (a) VALUES %s", [("x",)], retries=2)

        assert cursor.execute.call_count == 3  # initial + 2 retries

    def test_raises_on_non_transient_error_without_retry(self, mock_conn):
        """Non-transient OperationalError does NOT retry."""
        cursor = mock_conn.cursor.return_value.__enter__.return_value
        cursor.execute.side_effect = psycopg2.OperationalError("permission denied")

        with pytest.raises(psycopg2.OperationalError):
            write_batch(mock_conn, "INSERT INTO t (a) VALUES %s", [("x",)])

        # Only 1 attempt — no retry
        assert cursor.execute.call_count == 1

    def test_exponential_backoff_timing(self, mock_conn):
        """Backoff times follow exponential pattern with max cap."""
        import time

        cursor = mock_conn.cursor.return_value.__enter__.return_value
        cursor.execute.side_effect = psycopg2.OperationalError("could not serialize access")

        original_sleep = time.sleep
        slept_times = []

        def track_sleep(seconds):
            slept_times.append(seconds)
            return original_sleep(seconds / 1000)  # Don't actually wait

        with patch("time.sleep", side_effect=track_sleep):
            with pytest.raises(psycopg2.OperationalError):
                write_batch(mock_conn, "INSERT INTO t (a) VALUES %s", [("x",)],
                            retries=3, backoff_base=0.1, backoff_max=2.0)

        # Expected backoffs: 0.1, 0.2, 0.4 (capped at 2.0)
        assert len(slept_times) == 3
        assert abs(slept_times[0] - 0.1) < 0.01
        assert abs(slept_times[1] - 0.2) < 0.01
        assert abs(slept_times[2] - 0.4) < 0.01
