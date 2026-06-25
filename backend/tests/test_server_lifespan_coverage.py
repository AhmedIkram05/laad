"""Tests for server lifespan, _check_and_retrain_on_startup, and _do_retrain.

Covers the startup/shutdown lifecycle, model validation branching,
retrain success/failure paths, and the global exception handler —
areas NOT covered by test_server_routes.py.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeArtifactDir:
    """Plain class that supports ``ARTIFACT_DIR / filename`` via __truediv__.

    MagicMock's ``__truediv__`` is a *descriptor* on the class, so assigning
    ``mock.__truediv__ = fn`` does NOT override ``/``.  A plain class avoids
    this trap.
    """

    def __init__(self, file_exists: dict[str, bool]):
        self._file_exists = file_exists

    def __truediv__(self, name: str) -> MagicMock:
        p = MagicMock(spec=Path)
        p.exists.return_value = self._file_exists.get(name, False)
        return p


# ---------------------------------------------------------------------------
# Lifespan context-manager tests
# ---------------------------------------------------------------------------


class TestLifespan:
    """Test the lifespan() async context manager."""

    def test_lifespan_startup_and_shutdown(self, monkeypatch):
        """Full happy-path: DB init, scheduler start, yield, scheduler shutdown."""
        import backend.src.api.server as server_module

        monkeypatch.setattr(server_module, "_db_initialized", False)
        monkeypatch.setattr(server_module, "init_db", MagicMock())
        monkeypatch.setattr("backend.src.api.server.time.sleep", MagicMock())

        mock_scheduler = MagicMock()
        monkeypatch.setattr(server_module, "scheduler", mock_scheduler)
        monkeypatch.setenv("LAAD_ENV", "staging")
        monkeypatch.setattr(server_module, "_check_and_retrain_on_startup", MagicMock())

        async def _run():
            async with server_module.lifespan(server_module.app):
                mock_scheduler.start.assert_called_once()
                mock_scheduler.add_job.assert_called_once()
            mock_scheduler.shutdown.assert_called_once()

        asyncio.get_event_loop().run_until_complete(_run())

    def test_lifespan_skips_retrain_in_production(self, monkeypatch):
        """When LAAD_ENV=production, _check_and_retrain_on_startup is NOT called."""
        import backend.src.api.server as server_module

        monkeypatch.setattr(server_module, "_db_initialized", False)
        monkeypatch.setattr(server_module, "init_db", MagicMock())
        monkeypatch.setattr("backend.src.api.server.time.sleep", MagicMock())
        monkeypatch.setenv("LAAD_ENV", "production")

        mock_retrain = MagicMock()
        monkeypatch.setattr(
            server_module, "_check_and_retrain_on_startup", mock_retrain
        )

        mock_scheduler = MagicMock()
        monkeypatch.setattr(server_module, "scheduler", mock_scheduler)

        async def _run():
            async with server_module.lifespan(server_module.app):
                pass

        asyncio.get_event_loop().run_until_complete(_run())
        mock_retrain.assert_not_called()

    def test_lifespan_calls_retrain_when_not_production(self, monkeypatch):
        """When LAAD_ENV is empty/anything else, retrain check IS called."""
        import backend.src.api.server as server_module

        monkeypatch.setattr(server_module, "_db_initialized", False)
        monkeypatch.setattr(server_module, "init_db", MagicMock())
        monkeypatch.setattr("backend.src.api.server.time.sleep", MagicMock())
        monkeypatch.setenv("LAAD_ENV", "")

        mock_retrain = MagicMock()
        monkeypatch.setattr(
            server_module, "_check_and_retrain_on_startup", mock_retrain
        )

        mock_scheduler = MagicMock()
        monkeypatch.setattr(server_module, "scheduler", mock_scheduler)

        async def _run():
            async with server_module.lifespan(server_module.app):
                pass

        asyncio.get_event_loop().run_until_complete(_run())
        mock_retrain.assert_called_once()

    def test_lifespan_handles_db_init_failure(self, monkeypatch):
        """If _ensure_db_initialized raises, lifespan propagates the exception."""
        import backend.src.api.server as server_module

        monkeypatch.setattr(
            server_module,
            "_ensure_db_initialized",
            MagicMock(side_effect=Exception("DB unreachable")),
        )
        monkeypatch.setattr("backend.src.api.server.time.sleep", MagicMock())

        mock_scheduler = MagicMock()
        monkeypatch.setattr(server_module, "scheduler", mock_scheduler)

        async def _run():
            with pytest.raises(Exception, match="DB unreachable"):
                async with server_module.lifespan(server_module.app):
                    pass

        asyncio.get_event_loop().run_until_complete(_run())
        mock_scheduler.start.assert_not_called()


# ---------------------------------------------------------------------------
# _check_and_retrain_on_startup tests
# ---------------------------------------------------------------------------


class TestCheckAndRetrainOnStartup:
    """Test _check_and_retrain_on_startup branching logic."""

    def test_no_model_file_triggers_retrain(self, monkeypatch):
        """When xgb_classifier.joblib doesn't exist, _do_retrain is called."""
        import backend.src.api.server as server_module

        monkeypatch.setattr(
            server_module,
            "ARTIFACT_DIR",
            _FakeArtifactDir({"xgb_classifier.joblib": False}),
        )

        mock_do_retrain = MagicMock()
        monkeypatch.setattr(server_module, "_do_retrain", mock_do_retrain)

        server_module._check_and_retrain_on_startup()
        mock_do_retrain.assert_called_once()

    def test_valid_model_files_skip_retrain(self, monkeypatch):
        """When all three model files load successfully, retrain is skipped."""
        import backend.src.api.server as server_module

        monkeypatch.setattr(
            server_module,
            "ARTIFACT_DIR",
            _FakeArtifactDir(
                {
                    "xgb_classifier.joblib": True,
                    "isolation_forest.joblib": True,
                    "label_encoder.joblib": True,
                }
            ),
        )

        mock_do_retrain = MagicMock()
        monkeypatch.setattr(server_module, "_do_retrain", mock_do_retrain)

        mock_joblib = MagicMock()
        with patch.dict(sys.modules, {"joblib": mock_joblib}):
            server_module._check_and_retrain_on_startup()

        mock_do_retrain.assert_not_called()
        assert mock_joblib.load.call_count == 3

    def test_corrupted_model_files_trigger_retrain(self, monkeypatch):
        """When joblib.load raises on first file, retrain is triggered."""
        import backend.src.api.server as server_module

        monkeypatch.setattr(
            server_module,
            "ARTIFACT_DIR",
            _FakeArtifactDir(
                {
                    "xgb_classifier.joblib": True,
                    "isolation_forest.joblib": True,
                    "label_encoder.joblib": True,
                }
            ),
        )

        mock_joblib = MagicMock()
        mock_joblib.load.side_effect = Exception("pickle corruption")

        mock_do_retrain = MagicMock()
        monkeypatch.setattr(server_module, "_do_retrain", mock_do_retrain)

        with patch.dict(sys.modules, {"joblib": mock_joblib}):
            server_module._check_and_retrain_on_startup()

        mock_do_retrain.assert_called_once()

    def test_missing_second_model_file_triggers_retrain(self, monkeypatch):
        """When isolation_forest.joblib load fails, retrain is triggered."""
        import backend.src.api.server as server_module

        monkeypatch.setattr(
            server_module,
            "ARTIFACT_DIR",
            _FakeArtifactDir(
                {
                    "xgb_classifier.joblib": True,
                    "isolation_forest.joblib": True,
                    "label_encoder.joblib": True,
                }
            ),
        )

        mock_joblib = MagicMock()
        mock_joblib.load.side_effect = [
            MagicMock(),  # xgb loads fine
            Exception("isolation forest corrupted"),
        ]

        mock_do_retrain = MagicMock()
        monkeypatch.setattr(server_module, "_do_retrain", mock_do_retrain)

        with patch.dict(sys.modules, {"joblib": mock_joblib}):
            server_module._check_and_retrain_on_startup()

        mock_do_retrain.assert_called_once()

    def test_missing_third_model_file_triggers_retrain(self, monkeypatch):
        """When label_encoder.joblib load fails, retrain is triggered."""
        import backend.src.api.server as server_module

        monkeypatch.setattr(
            server_module,
            "ARTIFACT_DIR",
            _FakeArtifactDir(
                {
                    "xgb_classifier.joblib": True,
                    "isolation_forest.joblib": True,
                    "label_encoder.joblib": True,
                }
            ),
        )

        mock_joblib = MagicMock()
        mock_joblib.load.side_effect = [
            MagicMock(),  # xgb loads fine
            MagicMock(),  # iso loads fine
            Exception("encoder corrupted"),
        ]

        mock_do_retrain = MagicMock()
        monkeypatch.setattr(server_module, "_do_retrain", mock_do_retrain)

        with patch.dict(sys.modules, {"joblib": mock_joblib}):
            server_module._check_and_retrain_on_startup()

        mock_do_retrain.assert_called_once()


# ---------------------------------------------------------------------------
# _do_retrain tests — via the REAL function with importlib.reload mocked
# ---------------------------------------------------------------------------


class TestDoRetrain:
    """Test _do_retrain via the actual function with importlib.reload mocked.

    _do_retrain does:
        import importlib
        from backend.src.anomaly_detection.ml import train
        importlib.reload(train)
        train.train()

    The train module is already cached in sys.modules (server.py imports
    ARTIFACT_DIR from it at module level).  We patch ``importlib.reload``
    so it never re-executes the module source, and we patch the module's
    ``train`` attribute to control behaviour.
    """

    def test_success_path(self):
        """train.train() completes successfully."""
        import backend.src.api.server as server_module

        with (
            patch("backend.src.anomaly_detection.ml.train") as mock_train_mod,
            patch("importlib.reload", return_value=mock_train_mod) as mock_reload,
        ):
            server_module._do_retrain()

        mock_reload.assert_called_once()
        mock_train_mod.train.assert_called_once()

    def test_train_raises_exception(self):
        """train.train() raises — _do_retrain swallows it."""
        import backend.src.api.server as server_module

        with patch("backend.src.anomaly_detection.ml.train") as mock_train_mod:
            mock_train_mod.train.side_effect = RuntimeError("OOM")
            with patch("importlib.reload", return_value=mock_train_mod):
                # Must NOT raise
                server_module._do_retrain()

        mock_train_mod.train.assert_called_once()

    def test_reload_raises_import_error(self):
        """importlib.reload() raises — _do_retrain swallows it."""
        import backend.src.api.server as server_module

        with patch("importlib.reload", side_effect=ImportError("No xgboost")):
            # Must NOT raise
            server_module._do_retrain()

    def test_logger_error_called_on_train_failure(self):
        """logger.error is called when train.train() raises."""
        import backend.src.api.server as server_module

        with (
            patch("backend.src.anomaly_detection.ml.train") as mock_train_mod,
            patch("importlib.reload", return_value=mock_train_mod),
            patch("backend.src.api.server.logger") as mock_logger,
        ):
            mock_train_mod.train.side_effect = ValueError("bad data")
            server_module._do_retrain()

        mock_logger.error.assert_called_once()
        assert "Startup retrain failed" in mock_logger.error.call_args[0][0]

    def test_logger_error_called_on_reload_failure(self):
        """logger.error is called when importlib.reload raises."""
        import backend.src.api.server as server_module

        with (
            patch("importlib.reload", side_effect=ImportError("broken")),
            patch("backend.src.api.server.logger") as mock_logger,
        ):
            server_module._do_retrain()

        mock_logger.error.assert_called_once()
        assert "Startup retrain failed" in mock_logger.error.call_args[0][0]

    def test_logger_error_message_includes_exception(self):
        """The logged error message includes the exception details."""
        import backend.src.api.server as server_module

        with (
            patch("backend.src.anomaly_detection.ml.train") as mock_train_mod,
            patch("importlib.reload", return_value=mock_train_mod),
            patch("backend.src.api.server.logger") as mock_logger,
        ):
            mock_train_mod.train.side_effect = RuntimeError("disk full")
            server_module._do_retrain()

        # The second format arg should be the exception instance
        call_args = mock_logger.error.call_args
        assert "disk full" in str(call_args[0])


# ---------------------------------------------------------------------------
# Global exception handler (additional coverage beyond test_server_routes.py)
# ---------------------------------------------------------------------------


class TestGlobalExceptionHandlerAdditional:
    """Additional tests for the global exception handler."""

    def test_exception_handler_returns_500_with_json_detail(self):
        """Verify status code and JSON structure on unhandled exception."""
        from backend.src.api.server import app

        @app.get("/_test_exc_500")
        def _boom():
            raise RuntimeError("kaboom")

        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/_test_exc_500")

        assert resp.status_code == 500
        body = resp.json()
        assert body["detail"] == "An internal server error occurred"

        # cleanup
        app.routes[:] = [
            r for r in app.routes if getattr(r, "path", None) != "/_test_exc_500"
        ]

    def test_exception_handler_with_http_exception_not_caught(self):
        """HTTPException should propagate normally (not caught by generic handler)."""
        from fastapi import HTTPException
        from backend.src.api.server import app

        @app.get("/_test_http_exc")
        def _http_err():
            raise HTTPException(status_code=404, detail="Not found")

        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/_test_http_exc")

        # HTTPException has its own handler, so this returns 404, not 500
        assert resp.status_code == 404

        app.routes[:] = [
            r for r in app.routes if getattr(r, "path", None) != "/_test_http_exc"
        ]

    def test_exception_handler_logs_error(self):
        """Verify logger.error is called when exception handler fires."""
        from backend.src.api.server import app

        @app.get("/_test_exc_log")
        def _log_err():
            raise ValueError("log this")

        with patch("backend.src.api.server.logger") as mock_logger:
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.get("/_test_exc_log")

        assert resp.status_code == 500
        mock_logger.error.assert_called()

        app.routes[:] = [
            r for r in app.routes if getattr(r, "path", None) != "/_test_exc_log"
        ]


# ---------------------------------------------------------------------------
# Lifespan scheduler job configuration
# ---------------------------------------------------------------------------


class TestLifespanSchedulerConfig:
    """Verify the scheduler job is configured correctly during lifespan."""

    def test_cleanup_job_added_with_correct_interval(self, monkeypatch):
        """The cleanup job is added with 1-hour interval and misfire grace time."""
        import backend.src.api.server as server_module

        monkeypatch.setattr(server_module, "_db_initialized", True)
        monkeypatch.setenv("LAAD_ENV", "production")

        mock_scheduler = MagicMock()
        monkeypatch.setattr(server_module, "scheduler", mock_scheduler)
        monkeypatch.setattr(server_module, "_check_and_retrain_on_startup", MagicMock())

        async def _run():
            async with server_module.lifespan(server_module.app):
                call_args = mock_scheduler.add_job.call_args
                assert call_args[0][0] is not None  # callable
                assert call_args[0][1] == "interval"
                assert call_args[1]["hours"] == 1
                assert call_args[1]["id"] == "cleanup"
                assert call_args[1]["misfire_grace_time"] == 60

        asyncio.get_event_loop().run_until_complete(_run())

    def test_scheduler_shutdown_called_after_yield(self, monkeypatch):
        """scheduler.shutdown() is called exactly once when lifespan exits."""
        import backend.src.api.server as server_module

        monkeypatch.setattr(server_module, "_db_initialized", True)
        monkeypatch.setenv("LAAD_ENV", "production")
        monkeypatch.setattr(server_module, "_check_and_retrain_on_startup", MagicMock())

        mock_scheduler = MagicMock()
        monkeypatch.setattr(server_module, "scheduler", mock_scheduler)

        async def _run():
            async with server_module.lifespan(server_module.app):
                mock_scheduler.shutdown.assert_not_called()
            mock_scheduler.shutdown.assert_called_once()

        asyncio.get_event_loop().run_until_complete(_run())
