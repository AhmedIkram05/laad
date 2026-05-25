"""Tests for backend.src.database.config."""
from __future__ import annotations

import os
from unittest.mock import patch

import pytest


class TestDBConfig:
    def test_defaults_when_no_env(self):
        """When env vars are not set, defaults should be used."""
        with patch("backend.src.database.config.os.getenv") as mock_getenv:
            mock_getenv.return_value = None
            mock_getenv.side_effect = lambda key, default=None: default
            from importlib import reload
            import backend.src.database.config as cfg
            reload(cfg)
            assert cfg.DB_CONFIG["host"] == "localhost"
            assert cfg.DB_CONFIG["port"] == 5432
            assert cfg.DB_CONFIG["dbname"] == "atm_platform"
            assert cfg.DB_CONFIG["user"] == "atm_user"
            assert cfg.DB_CONFIG["password"] == ""

    def test_env_vars_override_defaults(self):
        """When env vars are set, they should override defaults."""
        env_vals = {
            "POSTGRES_HOST": "test-host",
            "POSTGRES_PORT": "9999",
            "POSTGRES_DB": "test_db",
            "POSTGRES_USER": "test_user",
            "POSTGRES_PASSWORD": "test_pass",
        }
        with patch("backend.src.database.config.os.getenv", side_effect=lambda k, d=None: env_vals.get(k, d)):
            from importlib import reload
            import backend.src.database.config as cfg
            reload(cfg)
            assert cfg.DB_CONFIG["host"] == "test-host"
            assert cfg.DB_CONFIG["port"] == 9999
            assert cfg.DB_CONFIG["dbname"] == "test_db"
            assert cfg.DB_CONFIG["user"] == "test_user"
            assert cfg.DB_CONFIG["password"] == "test_pass"
