"""Tests for admin ML retraining endpoint."""
from __future__ import annotations



class TestTrainingEndpoint:
    def test_training_endpoint_exists_in_router(self):
        from backend.src.admin.admin_router import router

        routes = [r.path for r in router.routes]
        assert "/admin/training" in routes

    def test_training_endpoint_is_post(self):
        from backend.src.admin.admin_router import router

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