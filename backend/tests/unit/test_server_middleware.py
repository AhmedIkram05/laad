"""Tests for server-level middleware: host validation and body size limit."""

from __future__ import annotations

from fastapi.testclient import TestClient


def _client() -> TestClient:
    from backend.src.api.server import app

    return TestClient(app)


class TestHostValidation:
    """TrustedHostMiddleware rejects unexpected Host headers."""

    def test_allowed_host_passes(self):
        resp = _client().get("/health")
        assert resp.status_code == 200

    def test_untrusted_host_rejected(self):
        resp = _client().get("/health", headers={"host": "evil.example.com"})
        assert resp.status_code == 400


class TestRequestBodyLimit:
    """Oversized bodies are rejected before reaching an endpoint."""

    def test_oversized_body_rejected(self, monkeypatch):
        import backend.src.api.server as server_module

        monkeypatch.setattr(server_module, "MAX_REQUEST_BODY_BYTES", 10)
        resp = _client().post("/auth/login", content=b"x" * 100)
        assert resp.status_code == 413

    def test_small_body_not_rejected_by_limit(self, monkeypatch):
        import backend.src.api.server as server_module

        monkeypatch.setattr(server_module, "MAX_REQUEST_BODY_BYTES", 10)
        # 5-byte body is under the limit, so the request reaches routing
        # (404/422, never 413).
        resp = _client().post("/nonexistent", content=b"12345")
        assert resp.status_code != 413
