"""Tests for backend.src.database.init_db."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestReadSchema:
    def test_read_schema_returns_contents(self):
        from backend.src.database.init_db import _read_schema
        content = _read_schema()
        assert content is not None
        assert len(content) > 0
        assert "CREATE TABLE" in content


class TestSeedAtms:
    def test_seed_atms_executes_insert(self):
        from backend.src.database.init_db import seed_atms
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_cursor.rowcount = 13

        with patch("backend.src.database.init_db.logger") as mock_logger:  # noqa: F841
            seed_atms(mock_conn)

        mock_conn.cursor.assert_called_once()
        assert mock_cursor.executemany.called
        call_args = mock_cursor.executemany.call_args
        assert "INSERT INTO atms" in call_args[0][0]
        # 10 ATMs + 3 servers
        assert len(call_args[0][1]) == 13

    def test_seed_atms_no_log_when_zero_affected(self):
        from backend.src.database.init_db import seed_atms
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_cursor.rowcount = 0

        with patch("backend.src.database.init_db.logger") as mock_logger:
            seed_atms(mock_conn)

        assert mock_logger.info.called


class TestSeedDefaultAdmin:
    def test_seed_default_admin_inserts(self):
        from backend.src.database.init_db import seed_default_admin
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_cursor.rowcount = 1

        with patch("backend.src.database.init_db.logger") as mock_logger:  # noqa: F841
            seed_default_admin(mock_conn)

        mock_conn.cursor.assert_called_once()
        call_args = mock_cursor.execute.call_args
        assert "INSERT INTO users" in call_args[0][0]

    def test_seed_default_admin_skips_when_exists(self):
        from backend.src.database.init_db import seed_default_admin
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_cursor.rowcount = 0

        with patch("backend.src.database.init_db.logger") as mock_logger:
            seed_default_admin(mock_conn)

        assert mock_logger.info.called


class TestSeedRetentionConfig:
    def test_seed_retention_config(self):
        from backend.src.database.init_db import seed_retention_config
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

        with patch("backend.src.database.init_db.logger") as mock_logger:  # noqa: F841
            seed_retention_config(mock_conn)

        mock_conn.cursor.assert_called_once()
        call_args = mock_cursor.execute.call_args
        assert "INSERT INTO retention_config" in call_args[0][0]


class TestInitDb:
    def test_init_db_success(self):
        from backend.src.database.init_db import init_db
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.side_effect = [mock_cursor, mock_cursor, mock_cursor]

        with patch("backend.src.database.init_db.get_conn", return_value=mock_conn), \
             patch("backend.src.database.init_db.release_conn"):
            with patch("backend.src.database.init_db.seed_atms") as mock_seed_atms:  # noqa: F841
                with patch("backend.src.database.init_db.seed_default_admin") as mock_seed_admin:  # noqa: F841
                    with patch("backend.src.database.init_db.seed_retention_config") as mock_seed_ret:  # noqa: F841
                        result = init_db(force=False)

        assert result is True
        mock_conn.commit.called

    def test_init_db_force_drops_tables(self):
        from backend.src.database.init_db import init_db
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

        # Override LAAD_ENV so the production guard doesn't block force=True
        with patch("backend.src.database.init_db.os.getenv", return_value="test"):
            with patch("backend.src.database.init_db.get_conn", return_value=mock_conn), \
                 patch("backend.src.database.init_db.release_conn"):
                with patch("backend.src.database.init_db.seed_atms"):
                    with patch("backend.src.database.init_db.seed_default_admin"):
                        with patch("backend.src.database.init_db.seed_retention_config"):
                            result = init_db(force=True)

        assert result is True
        # Should execute DROP statements (all in one multi-statement call)
        drop_args = " ".join(str(a) for a in mock_cursor.execute.call_args_list)
        assert "DROP VIEW IF EXISTS v_unified_analysis" in drop_args

    def test_init_db_raises_on_failure(self):
        from backend.src.database.init_db import init_db
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_cursor.execute.side_effect = Exception("DB error")

        with patch("backend.src.database.init_db.get_conn", return_value=mock_conn), \
             patch("backend.src.database.init_db.release_conn"):
            with pytest.raises(Exception, match="DB error"):
                init_db()
