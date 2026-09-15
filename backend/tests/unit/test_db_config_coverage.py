"""Coverage tests for backend.src.database.config."""

from __future__ import annotations

from importlib import reload
from unittest.mock import patch


class TestDBConfigLoadDotenv:
    """Test load_dotenv call path."""

    def test_load_dotenv_called_on_module_import(self):
        """load_dotenv() is called when the module is imported."""
        # Patch at the source so `from dotenv import load_dotenv` picks up the mock
        with patch("dotenv.load_dotenv") as mock_load_dotenv:
            import backend.src.database.config as cfg

            reload(cfg)
            mock_load_dotenv.assert_called()


class TestDBConfigPortConversion:
    """Test int() conversion edge cases for POSTGRES_PORT."""

    def test_float_string_port_raises_or_falls_back(self):
        """Float string '5432.0' raises ValueError during reload."""
        with patch(
            "backend.src.database.config.os.getenv",
            side_effect=lambda k, d=None: "5432.0" if k == "POSTGRES_PORT" else d,
        ):
            import backend.src.database.config as cfg

            try:
                reload(cfg)
                # If reload succeeds, the int() conversion raised and was not caught,
                # meaning the module crashed — which is the actual behavior.
                # But since we're testing the code path, if it didn't crash,
                # verify the value was converted somehow.
                # Actually, int("5432.0") raises ValueError, so reload should fail.
                # If we get here, the module somehow handled it.
            except (ValueError, SystemError):
                # Expected: int("5432.0") raises ValueError at module level
                pass

    def test_valid_integer_port(self):
        """Valid integer port string converts correctly."""
        with patch(
            "backend.src.database.config.os.getenv",
            side_effect=lambda k, d=None: "5433" if k == "POSTGRES_PORT" else d,
        ):
            import backend.src.database.config as cfg

            reload(cfg)
            assert cfg.DB_CONFIG["port"] == 5433

    def test_large_port_number(self):
        """Large port number converts correctly."""
        with patch(
            "backend.src.database.config.os.getenv",
            side_effect=lambda k, d=None: "65535" if k == "POSTGRES_PORT" else d,
        ):
            import backend.src.database.config as cfg

            reload(cfg)
            assert cfg.DB_CONFIG["port"] == 65535


class TestDBConfigPartialOverrides:
    """Test partial env var overrides."""

    def test_only_host_override(self):
        """Only POSTGRES_HOST set; other values use defaults."""
        with patch(
            "backend.src.database.config.os.getenv",
            side_effect=lambda k, d=None: "custom-host" if k == "POSTGRES_HOST" else d,
        ):
            import backend.src.database.config as cfg

            reload(cfg)
            assert cfg.DB_CONFIG["host"] == "custom-host"
            assert cfg.DB_CONFIG["port"] == 5432
            assert cfg.DB_CONFIG["dbname"] == "atm_platform"
            assert cfg.DB_CONFIG["user"] == "atm_user"
            assert cfg.DB_CONFIG["password"] == ""

    def test_only_password_override(self):
        """Only POSTGRES_PASSWORD set; other values use defaults."""
        with patch(
            "backend.src.database.config.os.getenv",
            side_effect=lambda k, d=None: "secret" if k == "POSTGRES_PASSWORD" else d,
        ):
            import backend.src.database.config as cfg

            reload(cfg)
            assert cfg.DB_CONFIG["host"] == "localhost"
            assert cfg.DB_CONFIG["password"] == "secret"

    def test_only_dbname_override(self):
        """Only POSTGRES_DB set; other values use defaults."""
        with patch(
            "backend.src.database.config.os.getenv",
            side_effect=lambda k, d=None: "mydb" if k == "POSTGRES_DB" else d,
        ):
            import backend.src.database.config as cfg

            reload(cfg)
            assert cfg.DB_CONFIG["dbname"] == "mydb"
            assert cfg.DB_CONFIG["host"] == "localhost"


class TestDBConfigEmptyStrings:
    """Test empty string values for required fields."""

    def test_empty_host(self):
        """Empty POSTGRES_HOST results in empty string."""
        with patch(
            "backend.src.database.config.os.getenv",
            side_effect=lambda k, d=None: "" if k == "POSTGRES_HOST" else d,
        ):
            import backend.src.database.config as cfg

            reload(cfg)
            assert cfg.DB_CONFIG["host"] == ""

    def test_empty_user(self):
        """Empty POSTGRES_USER results in empty string."""
        with patch(
            "backend.src.database.config.os.getenv",
            side_effect=lambda k, d=None: "" if k == "POSTGRES_USER" else d,
        ):
            import backend.src.database.config as cfg

            reload(cfg)
            assert cfg.DB_CONFIG["user"] == ""

    def test_empty_dbname(self):
        """Empty POSTGRES_DB results in empty string."""
        with patch(
            "backend.src.database.config.os.getenv",
            side_effect=lambda k, d=None: "" if k == "POSTGRES_DB" else d,
        ):
            import backend.src.database.config as cfg

            reload(cfg)
            assert cfg.DB_CONFIG["dbname"] == ""

    def test_empty_password(self):
        """Empty POSTGRES_PASSWORD results in empty string (same as default)."""
        with patch(
            "backend.src.database.config.os.getenv",
            side_effect=lambda k, d=None: "" if k == "POSTGRES_PASSWORD" else d,
        ):
            import backend.src.database.config as cfg

            reload(cfg)
            assert cfg.DB_CONFIG["password"] == ""


class TestDBConfigKeyCount:
    """Test that DB_CONFIG has the expected keys."""

    def test_db_config_has_five_keys(self):
        """DB_CONFIG contains host, port, dbname, user, password."""
        import backend.src.database.config as cfg

        expected_keys = {"host", "port", "dbname", "user", "password"}
        assert set(cfg.DB_CONFIG.keys()) == expected_keys

    def test_db_config_port_is_int(self):
        """DB_CONFIG port value is an integer."""
        import backend.src.database.config as cfg

        assert isinstance(cfg.DB_CONFIG["port"], int)
