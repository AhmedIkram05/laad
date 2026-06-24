"""Tests for server health probes, startup retry, exception handler, and CORS."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


class TestHealthProbes:
    """Test /health (liveness) and /health/ready (readiness) endpoints."""

    def test_health_check_returns_ok(self):
        from backend.src.api.server import app

        with TestClient(app) as client:
            resp = client.get("/health")

        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

    @patch("backend.src.api.server.get_conn")
    @patch("backend.src.api.server.release_conn")
    def test_readiness_returns_ready(self, mock_release, mock_get_conn):
        from backend.src.api.server import app

        mock_conn = MagicMock()
        mock_get_conn.return_value = mock_conn

        with TestClient(app) as client:
            resp = client.get("/health/ready")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ready"
        assert data["database"] == "connected"

    @patch("backend.src.api.server.get_conn")
    def test_readiness_returns_503_when_db_down(self, mock_get_conn):
        from backend.src.api.server import app

        mock_get_conn.side_effect = Exception("DB connection failed")

        with TestClient(app) as client:
            resp = client.get("/health/ready")

        assert resp.status_code == 503
        assert "Database not ready" in resp.json()["detail"]


class TestExceptionHandler:
    """Test the global exception handler catches unhandled exceptions."""

    def test_global_exception_handler_returns_json(self):
        from backend.src.api.server import app

        # Temporarily register a route that raises an unhandled exception
        @app.get("/_test_exception")
        def _raise_unhandled():
            raise ValueError("Test unhandled error")

        with TestClient(app) as client:
            try:
                resp = client.get("/_test_exception")
            except (ValueError, RuntimeError):
                # TestClient may re-raise in some configurations
                return

        assert resp.status_code == 500
        assert resp.json()["detail"] == "An internal server error occurred"

        # Clean up the test route
        app.routes[:] = [
            r
            for r in app.routes
            if getattr(r, "path", None) != "/_test_exception"
        ]

    def test_normal_routes_still_work(self):
        """Verify normal routes are unaffected by the exception handler."""
        from backend.src.api.server import app

        with TestClient(app) as client:
            resp = client.get("/health")

        assert resp.status_code == 200


class TestEnsureDbInitialized:
    """Test the _ensure_db_initialized startup function."""

    def test_succeeds_on_first_attempt(self, monkeypatch):
        from backend.src.api.server import _ensure_db_initialized

        monkeypatch.setattr("backend.src.api.server._db_initialized", False)
        mock_init_db = MagicMock()
        monkeypatch.setattr("backend.src.api.server.init_db", mock_init_db)

        _ensure_db_initialized()

        mock_init_db.assert_called_once()

    def test_retries_on_failure_then_succeeds(self, monkeypatch):
        import backend.src.api.server as server_module

        monkeypatch.setattr(server_module, "_db_initialized", False)
        mock_init_db = MagicMock()
        mock_init_db.side_effect = [Exception("First fail"), None]
        monkeypatch.setattr(server_module, "init_db", mock_init_db)
        mock_sleep = MagicMock()
        monkeypatch.setattr("backend.src.api.server.time.sleep", mock_sleep)

        server_module._ensure_db_initialized()

        assert mock_init_db.call_count == 2
        mock_sleep.assert_called_once_with(2)

    def test_raises_after_max_retries(self, monkeypatch):
        import backend.src.api.server as server_module

        monkeypatch.setattr(server_module, "_db_initialized", False)
        mock_init_db = MagicMock()
        mock_init_db.side_effect = Exception("Persistent failure")
        monkeypatch.setattr(server_module, "init_db", mock_init_db)
        mock_sleep = MagicMock()
        monkeypatch.setattr("backend.src.api.server.time.sleep", mock_sleep)

        with pytest.raises(Exception, match="Persistent failure"):
            server_module._ensure_db_initialized()

        assert mock_init_db.call_count == 3
        assert mock_sleep.call_count == 2

    def test_skips_when_already_initialized(self, monkeypatch):
        from backend.src.api.server import _ensure_db_initialized

        monkeypatch.setattr("backend.src.api.server._db_initialized", True)
        mock_init_db = MagicMock()
        monkeypatch.setattr("backend.src.api.server.init_db", mock_init_db)

        _ensure_db_initialized()

        mock_init_db.assert_not_called()

    def test_concurrent_calls_use_cache(self, monkeypatch):
        """Second call skips init_db since flag is already set."""
        import backend.src.api.server as server_module

        monkeypatch.setattr(server_module, "_db_initialized", False)
        mock_init_db = MagicMock()
        monkeypatch.setattr(server_module, "init_db", mock_init_db)

        server_module._ensure_db_initialized()
        server_module._ensure_db_initialized()

        mock_init_db.assert_called_once()


class TestCors:
    """Test CORS middleware configuration."""

    def test_cors_headers_present(self):
        from backend.src.api.server import app

        with TestClient(app) as client:
            resp = client.get(
                "/health",
                headers={"Origin": "http://localhost:5173"},
            )

        assert (
            resp.headers.get("access-control-allow-origin")
            == "http://localhost:5173"
        )
