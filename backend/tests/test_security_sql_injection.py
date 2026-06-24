"""SQL Injection Security Tests — validates parameterized query patterns.

The codebase consistently uses psycopg2 parameterized queries (%s placeholders),
which inherently prevent SQL injection. These tests verify that:
  1. SQL injection payloads in query parameters do not produce 500 errors
  2. The API returns appropriate 4xx status codes or gracefully handles input
  3. All major endpoint groups that accept user input are covered
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from backend.src.api.server import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def admin_token(client):
    resp = client.post("/auth/login", data={"username": "admin", "password": "admin"})
    assert resp.status_code == 200
    return resp.json()["access_token"]


SQLI_PAYLOADS = [
    "' OR '1'='1",
    "' OR 1=1--",
    "' UNION SELECT * FROM users--",
    "admin'--",
    "'; DROP TABLE anomalies; --",
    "1' AND SLEEP(1)--",
    "' OR '1'='1' /*",
    "\\\"; SELECT * FROM users;",
    "' WAITFOR DELAY '0:0:5'--",
    "<script>alert('xss')</script>",
]


class TestSQLInjection:
    """10 tests: SQL injection payloads across all endpoint groups."""

    # ── 1-5: Five distinct SQLi payloads on /anomalies query params ───

    @pytest.mark.parametrize(
        "payload",
        [
            pytest.param(SQLI_PAYLOADS[0], id="tautology"),
            pytest.param(SQLI_PAYLOADS[1], id="comment_bypass"),
            pytest.param(SQLI_PAYLOADS[4], id="destructive"),
            pytest.param(SQLI_PAYLOADS[3], id="auth_bypass"),
            pytest.param(SQLI_PAYLOADS[5], id="time_delay"),
        ],
    )
    def test_anomalies_filter_injection(self, client, admin_token, payload):
        """SQLi in anomalies query params should never produce 500."""
        headers = {"Authorization": f"Bearer {admin_token}"}
        resp = client.get(f"/anomalies?atm_id={payload}&severity={payload}", headers=headers)
        assert resp.status_code < 500

    # ── 6: SQLi on login endpoint ─────────────────────────────────────

    def test_login_injection(self, client):
        """SQLi payload in login username returns 401, never 500."""
        resp = client.post(
            "/auth/login",
            data={"username": SQLI_PAYLOADS[0], "password": "irrelevant"},
        )
        assert resp.status_code == 401

    # ── 7: SQLi on register endpoint ──────────────────────────────────

    def test_register_injection(self, client):
        """SQLi payload in register username should not produce 500."""
        resp = client.post(
            "/auth/register",
            json={"username": f"{SQLI_PAYLOADS[4]}_{__import__('time').time_ns()}", "password": "TestPass123"},
        )
        assert resp.status_code < 500

    # ── 8: SQLi on analytics endpoint ─────────────────────────────────

    def test_analytics_injection(self, client):
        """SQLi payload in analytics sources parameter."""
        resp = client.get(f"/api/analytics/events?sources={SQLI_PAYLOADS[0]}")
        assert resp.status_code < 500
        resp2 = client.get(f"/api/analytics/metrics?sources={SQLI_PAYLOADS[2]}")
        assert resp2.status_code < 500

    # ── 9: SQLi on analysis endpoint ──────────────────────────────────

    def test_analysis_injection(self, client, admin_token):
        """SQLi payload in analysis parameters."""
        headers = {"Authorization": f"Bearer {admin_token}"}
        resp = client.get(
            f"/analysis/metrics?hours={SQLI_PAYLOADS[0]}&bucket_minutes={SQLI_PAYLOADS[1]}",
            headers=headers,
        )
        assert resp.status_code < 500
        resp2 = client.get(
            f"/analysis/detailed?Anomaly={SQLI_PAYLOADS[2]}",
            headers=headers,
        )
        assert resp2.status_code < 500

    # ── 10: Edge case special characters ──────────────────────────────

    @pytest.mark.parametrize(
        "char",
        [
            pytest.param("\\", id="backslash"),
            pytest.param("%", id="percent"),
            pytest.param("_", id="underscore"),
            pytest.param("", id="empty"),
        ],
    )
    def test_special_chars(self, client, admin_token, char):
        """Special characters that could affect SQL parsing."""
        headers = {"Authorization": f"Bearer {admin_token}"}
        resp = client.get(f"/anomalies?severity={char}", headers=headers)
        assert resp.status_code < 500
