"""Direct unit tests for cleanup module functions.

Uses mocked connections to test batched_delete, batched_delete_all,
edge cases, and error handling without requiring real DB state.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from backend.src.admin.cleanup import batched_delete, batched_delete_all, run_wipe, TABLE_CONFIG


@pytest.fixture
def mock_conn():
    """Return a MagicMock connection with a cursor factory."""
    conn = MagicMock()
    cursor = MagicMock()
    cursor.rowcount = 0
    conn.cursor.return_value = cursor
    conn.cursor.return_value.__enter__.return_value = cursor
    return conn


class TestBatchedDelete:
    def test_deletes_rows_in_batches(self, mock_conn):
        """First batch returns 5000 rows, second returns 0 → total = 5000."""
        cursor = mock_conn.cursor.return_value.__enter__.return_value
        cursor.rowcount = 5000
        # Defer rowcount change to second execute call so the
        # batched_delete while-loop terminates instead of looping forever.
        execute_call_count = [0]
        original_execute = cursor.execute

        def side_effect(*args, **kwargs):
            execute_call_count[0] += 1
            if execute_call_count[0] >= 2:
                cursor.rowcount = 0
            return original_execute(*args, **kwargs)

        cursor.execute = side_effect

        result = batched_delete(mock_conn, "events", "timestamp",
                                "2026-01-01T00:00:00")

        assert result == 5000
        assert mock_conn.commit.call_count >= 2

    def test_no_rows_to_delete(self, mock_conn):
        """When rowcount is 0 on first batch, total = 0."""
        cursor = mock_conn.cursor.return_value.__enter__.return_value
        cursor.rowcount = 0

        result = batched_delete(mock_conn, "events", "timestamp",
                                "2026-01-01T00:00:00")

        assert result == 0
        mock_conn.commit.assert_called_once()

    def test_multiple_batches(self, mock_conn):
        """3 batches: 5000, 5000, 0 → total = 10000."""
        cursor = mock_conn.cursor.return_value.__enter__.return_value
        cursor.rowcount = 5000

        # Rowcount sequence: 5000, 5000, 0
        results = [5000, 5000, 0]
        original_execute = cursor.execute

        def side_effect(*args, **kwargs):
            nonlocal results
            cursor.rowcount = results.pop(0) if results else 0
            return original_execute(*args, **kwargs)

        cursor.execute = side_effect

        result = batched_delete(mock_conn, "events", "timestamp",
                                "2026-01-01T00:00:00")

        assert result == 10000
        assert mock_conn.commit.call_count >= 2

    def test_invalid_table_raises_value_error(self, mock_conn):
        with pytest.raises(ValueError, match="Invalid table"):
            batched_delete(mock_conn, "nonexistent_table", "timestamp",
                           "2026-01-01T00:00:00")

    def test_applies_extra_condition(self, mock_conn):
        cursor = mock_conn.cursor.return_value.__enter__.return_value
        cursor.rowcount = 0

        batched_delete(mock_conn, "anomalies", "detected_at",
                       "2026-01-01T00:00:00", extra_cond="AND is_active = 0")

        sql = cursor.execute.call_args[0][0]
        assert "AND is_active = 0" in sql


class TestBatchedDeleteAll:
    def test_deletes_all_rows(self, mock_conn):
        """batched_delete_all deletes until empty."""
        cursor = mock_conn.cursor.return_value.__enter__.return_value
        results = [5000, 5000, 0]

        def side_effect(*args, **kwargs):
            cursor.rowcount = results.pop(0) if results else 0

        cursor.execute = side_effect

        result = batched_delete_all(mock_conn, "events")
        assert result == 10000

    def test_empty_table(self, mock_conn):
        cursor = mock_conn.cursor.return_value.__enter__.return_value
        cursor.rowcount = 0

        result = batched_delete_all(mock_conn, "events")
        assert result == 0

    def test_invalid_table_raises_value_error(self, mock_conn):
        with pytest.raises(ValueError, match="Invalid table"):
            batched_delete_all(mock_conn, "invalid_table")


class TestRunWipe:
    def test_run_wipe_returns_deleted_dict(self):
        """run_wipe returns correct structure and iterates all tables."""
        mock_conn = MagicMock()
        cursor = MagicMock()
        cursor.rowcount = 0
        mock_conn.cursor.return_value = cursor
        mock_conn.cursor.return_value.__enter__.return_value = cursor

        with patch("backend.src.admin.cleanup.get_conn", return_value=mock_conn), \
             patch("backend.src.admin.cleanup.release_conn"):
            result = run_wipe()

        assert result["action"] == "wipe"
        assert "deleted" in result
        for t_config in TABLE_CONFIG:
            assert t_config[0] in result["deleted"]
