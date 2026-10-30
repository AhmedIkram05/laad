"""Tests for admin ML retraining endpoint."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest
from fastapi import BackgroundTasks, HTTPException

from backend.src.admin.admin_router import router


class TestTrainingEndpoint:
    def test_training_endpoint_exists_in_router(self):
        routes = [r.path for r in router.routes]
        assert "/admin/training" in routes

    def test_training_endpoint_is_post(self):
        for route in router.routes:
            if route.path == "/admin/training":
                assert "POST" in route.methods, "Training endpoint must be POST"
                break

    def test_training_response_model(self):
        from backend.src.admin.admin_router import TrainingResponse

        resp = TrainingResponse(status="started", message="test", windows_loaded=None)
        assert resp.status == "started"
        assert resp.message == "test"
        assert resp.windows_loaded is None


class TestTrainingLock:
    def test_returns_409_when_training_already_running(self):
        from backend.src.admin import admin_router

        admin_router._training_lock.acquire()
        try:
            bg = BackgroundTasks()
            with pytest.raises(HTTPException) as excinfo:
                admin_router.trigger_training(bg)
            assert excinfo.value.status_code == 409
            assert excinfo.value.detail == "Training already in progress"
            # Nothing is scheduled while a run is already in flight.
            assert bg.tasks == []
        finally:
            admin_router._training_lock.release()

    def test_background_task_releases_lock_even_on_failure(self):
        from backend.src.admin import admin_router

        bg = BackgroundTasks()
        response = admin_router.trigger_training(bg)
        assert response.status == "started"
        assert len(bg.tasks) == 1
        assert admin_router._training_lock.locked()

        # Running the scheduled task releases the lock, even when the
        # training run itself raises.
        with patch(
            "backend.src.anomaly_detection.ml.train.train",
            side_effect=RuntimeError("boom"),
        ) as mock_train:
            asyncio.run(bg())

        mock_train.assert_called_once()
        assert not admin_router._training_lock.locked()
