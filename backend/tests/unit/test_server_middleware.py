"""Tests for server-level middleware: host validation and body size limit."""

from __future__ import annotations

from fastapi.testclient import TestClient


def _client() -> TestClient:
    from backend.src.api.server import app

    return TestClient(app)


class TestHostValidation:
    """TrustedHostMiddleware rejects unexpected Host headers.

    /health is exempt (see HealthExemptTrustedHostMiddleware): the ALB sends
    the target's private IP as the Host header on health checks.
    """

    def test_allowed_host_passes(self):
        resp = _client().get("/health")
        assert resp.status_code == 200

    def test_health_exempt_from_host_validation(self):
        resp = _client().get("/health", headers={"host": "10.0.3.42:8000"})
        assert resp.status_code == 200

    def test_localhost_host_passes(self):
        resp = _client().get("/nonexistent", headers={"host": "localhost"})
        assert resp.status_code == 404

    def test_untrusted_host_rejected(self):
        resp = _client().get("/nonexistent", headers={"host": "evil.example.com"})
        assert resp.status_code == 400

    def test_allowed_wildcard_host_passes(self):
        from fastapi import FastAPI

        from backend.src.api.server import HealthExemptTrustedHostMiddleware

        wildcard_app = FastAPI()
        wildcard_app.add_middleware(
            HealthExemptTrustedHostMiddleware,
            allowed_hosts=[
                "*.cloudfront.net",
                "*.elb.amazonaws.com",
                "localhost",
                "127.0.0.1",
            ],
            www_redirect=False,
        )
        client = TestClient(wildcard_app)
        for host in (
            "d123.cloudfront.net",
            "laad-alb-abc.eu-west-2.elb.amazonaws.com",
        ):
            resp = client.get("/health/ready", headers={"host": host})
            assert resp.status_code == 404, f"{host} should pass host validation"
        resp = client.get("/health/ready", headers={"host": "evil.example.com"})
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

    def test_oversized_413_carries_cors_headers(self, monkeypatch):
        import backend.src.api.server as server_module

        monkeypatch.setattr(server_module, "MAX_REQUEST_BODY_BYTES", 10)
        resp = _client().post(
            "/auth/login",
            content=b"x" * 100,
            headers={"origin": "http://localhost:5173"},
        )
        assert resp.status_code == 413
        # CORS is registered after the limit middleware so its headers are on
        # the 413 too.
        assert (
            resp.headers.get("access-control-allow-origin") == "http://localhost:5173"
        )

    def test_chunked_oversized_body_rejected(self, monkeypatch):
        import backend.src.api.server as server_module

        monkeypatch.setattr(server_module, "MAX_REQUEST_BODY_BYTES", 32)

        def chunks():
            # Three chunks totalling 75 bytes, sent without Content-Length.
            yield b'{"query": "'
            yield b"x" * 64
            yield b'"}'

        # A JSON body forces FastAPI to read the body, so the counting
        # receive runs; auth/validation happen only after.
        resp = _client().post(
            "/api/rag/query",
            content=chunks(),
            headers={"content-type": "application/json"},
        )
        assert resp.status_code == 413

    def test_chunked_small_body_passes_through(self, monkeypatch):
        import backend.src.api.server as server_module

        monkeypatch.setattr(server_module, "MAX_REQUEST_BODY_BYTES", 1024)

        def chunks():
            yield b'{"query": '
            yield b'"hello"}'

        # Under the cap the body streams through; the request reaches routing
        # (auth/validation errors are fine, but it must not be a 413).
        resp = _client().post(
            "/api/rag/query",
            content=chunks(),
            headers={"content-type": "application/json"},
        )
        assert resp.status_code != 413
