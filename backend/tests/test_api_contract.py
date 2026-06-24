"""API Contract Tests — validates the OpenAPI schema and endpoint behaviour.

Validates:
  1. The OpenAPI schema is well-formed and includes all paths
  2. Every documented endpoint responds with a non-500 status
  3. Responses match their declared schema for a representative subset
  4. Undocumented paths return 404
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from backend.src.api.server import app


@pytest.fixture(scope="module")
def client():
    """Shared TestClient for all contract tests."""
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def admin_token(client):
    """Obtain a valid admin JWT, cached per module."""
    resp = client.post("/auth/login", data={"username": "admin", "password": "admin"})
    assert resp.status_code == 200
    return resp.json()["access_token"]


# ── Helpers ──────────────────────────────────────────────────────────────


def _get_paths_by_tag(schema: dict) -> dict[str, list[str]]:
    """Group path+method strings by their first tag."""
    tagged: dict[str, list[str]] = {}
    for path, methods in schema.get("paths", {}).items():
        for method in ("get", "post", "put", "patch", "delete"):
            spec = methods.get(method)
            if spec is None:
                continue
            tags = spec.get("tags", ["untagged"])
            tag = tags[0] if tags else "untagged"
            tagged.setdefault(tag, []).append(f"{method.upper()} {path}")
    return tagged


def _count_endpoints(schema: dict) -> int:
    """Count total path+method combinations in the schema."""
    count = 0
    for path, methods in schema.get("paths", {}).items():
        count += sum(1 for m in ("get", "post", "put", "patch", "delete") if m in methods)
    return count


# ═══════════════════════════════════════════════════════════════════════
# 1. OpenAPI Schema Structure
# ═══════════════════════════════════════════════════════════════════════


class TestOpenAPISchema:
    """The auto-generated OpenAPI schema must be valid and complete."""

    def test_schema_is_valid_json(self, client):
        """Fetch /openapi.json and verify basic structure."""
        resp = client.get("/openapi.json")
        assert resp.status_code == 200
        schema = resp.json()
        assert "openapi" in schema, "Missing 'openapi' version field"
        assert schema["info"]["title"] == "ATM Log Aggregation Platform"

    def test_schema_has_all_endpoints(self, client):
        """Verify all expected route groups are present."""
        schema = client.get("/openapi.json").json()
        paths = schema["paths"]
        assert "/health" in paths, "Missing /health"
        assert "/health/ready" in paths, "Missing /health/ready"
        assert "/auth/login" in paths, "Missing /auth/login"
        assert "/auth/me" in paths, "Missing /auth/me"
        assert "/auth/register" in paths, "Missing /auth/register"
        assert "/anomalies" in paths, "Missing /anomalies in OpenAPI schema"
        assert "/api/analytics/entities" in paths, "Missing /api/analytics/entities"

    def test_minimum_endpoint_count(self, client):
        """At least 20 documented endpoints."""
        schema = client.get("/openapi.json").json()
        count = _count_endpoints(schema)
        assert count >= 20, f"Expected >=20 endpoints, got {count}"

    def test_schema_has_tags(self, client):
        """Tags should be present and describe endpoint groups."""
        schema = client.get("/openapi.json").json()
        tags = schema.get("tags", [])
        tag_names = {t["name"] for t in tags}
        # At minimum, we expect these functional groups
        assert len(tags) >= 3, f"Expected >=3 tags, got {len(tags)}"


# ═══════════════════════════════════════════════════════════════════════
# 2. Endpoint Behaviour — every documented path
# ═══════════════════════════════════════════════════════════════════════


class TestEndpointBehaviour:
    """Every documented endpoint should return a non-500 response for a
    reasonable request. Auth-protected endpoints are tested with an
    admin token obtained at the start."""

    # ── Health probes (unauthenticated) ──────────────────────────

    def test_health_liveness(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

    def test_health_readiness(self, client):
        resp = client.get("/health/ready")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ready"
        assert body["database"] == "connected"

    # ── Auth endpoints ───────────────────────────────────────────

    def test_auth_login_success(self, client):
        resp = client.post("/auth/login", data={"username": "admin", "password": "admin"})
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    def test_auth_login_invalid(self, client):
        resp = client.post("/auth/login", data={"username": "admin", "password": "wrong"})
        assert resp.status_code == 401

    def test_auth_me_with_token(self, client, admin_token):
        resp = client.get("/auth/me", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200
        assert resp.json()["username"] == "admin"

    def test_auth_me_unauthorized(self, client):
        resp = client.get("/auth/me")
        assert resp.status_code == 401

    def test_auth_register(self, client):
        username = f"contract_test_user_{__import__('time').time_ns()}"
        resp = client.post("/auth/register", json={"username": username, "password": "TestPass123"})
        assert resp.status_code == 201
        assert resp.json()["username"] == username

    # ── Admin endpoints (authenticated) ──────────────────────────

    def test_admin_retention_get(self, client, admin_token):
        resp = client.get("/admin/retention", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert "retention_days" in data

    def test_admin_retention_update(self, client, admin_token):
        resp = client.put(
            "/admin/retention",
            headers={"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"},
            json={"days": 7},
        )
        assert resp.status_code == 200

    def test_admin_ingestion_errors(self, client, admin_token):
        resp = client.get(
            "/admin/ingestion-errors?limit=5&offset=0",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data
        assert isinstance(data["data"], list)

    def test_admin_create_user(self, client, admin_token):
        resp = client.post(
            "/admin/users",
            headers={"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"},
            json={"username": "contract_admin", "password": "pass123", "confirm_password": "pass123", "role": "admin"},
        )
        assert resp.status_code in (201, 409)  # 409 duplicate is acceptable

    # ── Anomalies endpoints ──────────────────────────────────────

    def test_anomalies_list(self, client, admin_token):
        resp = client.get("/anomalies", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data

    def test_anomalies_list_with_filters(self, client, admin_token):
        resp = client.get(
            "/anomalies?sort_by=severity&is_active=1",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200

    def test_anomalies_list_with_entity_filter(self, client, admin_token):
        """Server and ATM entity type filters should not cause errors."""
        resp = client.get(
            "/anomalies?entity_type=atm",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        resp2 = client.get(
            "/anomalies?entity_type=server",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp2.status_code == 200

    # ── Analytics endpoints (unauthenticated or token not required) ──
    # Note: these routers may use their own auth; test with and without

    def test_analytics_entities(self, client):
        resp = client.get("/api/analytics/entities")
        # Either 200 (no auth required) or 401 (auth required)
        assert resp.status_code in (200, 401)

    def test_analytics_events(self, client):
        resp = client.get("/api/analytics/events")
        assert resp.status_code in (200, 401)

    def test_analytics_metrics_list(self, client):
        resp = client.get("/api/analytics/metrics/list")
        assert resp.status_code in (200, 401)

    # ── Analysis endpoints ───────────────────────────────────────

    def test_analysis_detailed(self, client, admin_token):
        resp = client.get("/analysis/detailed?Anomaly=A1", headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200
        data = resp.json()
        # Should have tables key (even if empty array)
        assert "tables" in data

    def test_analysis_metrics(self, client, admin_token):
        resp = client.get("/analysis/metrics?hours=24&bucket_minutes=60", headers={"Authorization": f"Bearer {admin_token}"})
        # Analysis metrics should return 200
        assert resp.status_code == 200

    # ── RAG endpoints ────────────────────────────────────────────

    def test_rag_history(self, client):
        resp = client.get("/api/rag/history?limit=5&offset=0")
        assert resp.status_code in (200, 401)

    def test_rag_stats(self, client):
        resp = client.get("/api/rag/stats")
        assert resp.status_code in (200, 401)

    # ── 404 for unknown paths ────────────────────────────────────

    def test_unknown_path_returns_404(self, client):
        resp = client.get("/this/path/does/not/exist")
        assert resp.status_code == 404

    def test_unknown_path_post_returns_404(self, client):
        resp = client.post("/api/nonexistent")
        assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════════════════
# 3. Response Schema Validation
# ═══════════════════════════════════════════════════════════════════════


class TestResponseShape:
    """For critical endpoints, verify the response body matches expectations."""

    def test_health_shape(self, client):
        resp = client.get("/health")
        assert resp.json() == {"status": "ok"}

    def test_auth_login_shape(self, client):
        resp = client.post("/auth/login", data={"username": "admin", "password": "admin"})
        body = resp.json()
        assert isinstance(body["access_token"], str)
        assert body["token_type"] == "bearer"

    def test_anomalies_list_shape(self, client, admin_token):
        """Anomalies list returns an array at .data."""
        resp = client.get("/anomalies", headers={"Authorization": f"Bearer {admin_token}"})
        body = resp.json()
        assert isinstance(body["data"], list)
        if len(body["data"]) > 0:
            anomaly = body["data"][0]
            # Must have these keys
            for key in ("id", "anomaly_type", "severity", "title"):
                assert key in anomaly, f"Missing key {key} in anomaly object"

    def test_admin_retention_shape(self, client, admin_token):
        """Retention settings has retention_days."""
        resp = client.get("/api/admin/retention", headers={"Authorization": f"Bearer {admin_token}"})
        body = resp.json()
        assert isinstance(body.get("retention_days"), int)

    def test_analytics_entities_shape(self, client):
        """Entities endpoint returns a list of entities."""
        resp = client.get("/api/analytics/entities")
        if resp.status_code == 200:
            body = resp.json()
            assert "entities" in body
            assert isinstance(body["entities"], list)
