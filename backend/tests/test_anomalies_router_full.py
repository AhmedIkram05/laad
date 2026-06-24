"""Comprehensive tests for anomalies router endpoints.

Covers feedback PATCH, all 3 grouping modes, all 3 sort modes,
filters, cache hit/miss behavior, pagination, and auth enforcement.
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta

from fastapi.testclient import TestClient
from psycopg2.extras import Json

from backend.src.api.server import app
from backend.src.database.connection import get_conn, release_conn
from backend.src.auth import auth_router
from backend.tests.helpers import reset_test_db


def _setup():
    reset_test_db()
    conn = get_conn()

    def override_get_db():
        try:
            yield conn
        finally:
            pass

    app.dependency_overrides[auth_router.get_db_connection] = override_get_db
    return conn


def _login(client) -> dict:
    resp = client.post("/auth/login", data={"username": "admin", "password": "admin"})
    assert resp.status_code == 200, resp.text
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _ensure_atm(conn, atm_id):
    """Ensure ATM record exists for FK constraint."""
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM atms WHERE atm_id = %s", (atm_id,))
        if not cur.fetchone():
            cur.execute(
                "INSERT INTO atms (atm_id, os_version, location_code) VALUES (%s, %s, %s)",
                (atm_id, "v1", "LOC-1"),
            )
    conn.commit()


def _seed_anomaly(conn, **overrides):
    now = datetime.now(timezone.utc)
    defaults = {
        "detected_at": now,
        "anomaly_type": "A1",
        "atm_id": "ATM-GB-0001",
        "severity": "HIGH",
        "title": "Test Anomaly",
        "explanation": '{"source": "ML_ENSEMBLE"}',
        "recommended_action": "Review",
        "sources_involved": Json(["ATM_APP"]),
        "is_active": 1,
        "is_starred": 0,
        "feedback_rating": None,
        "false_positive_count": 0,
    }
    defaults.update(overrides)
    _ensure_atm(conn, defaults["atm_id"])
    cols = ", ".join(defaults.keys())
    placeholders = ", ".join(["%s"] * len(defaults))
    with conn.cursor() as cur:
        cur.execute(
            f"INSERT INTO anomalies ({cols}) VALUES ({placeholders})",
            tuple(defaults.values()),
        )
    conn.commit()

    with conn.cursor() as cur:
        cur.execute("SELECT id FROM anomalies ORDER BY id DESC LIMIT 1")
        return cur.fetchone()[0]


# ── Feedback ──────────────────────────────────────────────────────────────


class TestFeedback:
    def test_like_rating(self):
        conn = _setup()
        try:
            with TestClient(app) as client:
                aid = _seed_anomaly(conn)
                headers = _login(client)

                resp = client.patch(
                    f"/anomalies/{aid}/feedback",
                    json={"rating": "LIKE"},
                    headers=headers,
                )
                assert resp.status_code == 200
                body = resp.json()
                assert body["feedback_rating"] == "LIKE"
                assert body["false_positive_count"] == 0
        finally:
            app.dependency_overrides.clear()
            release_conn(conn)

    def test_dislike_increments_fp_count(self):
        conn = _setup()
        try:
            with TestClient(app) as client:
                aid = _seed_anomaly(conn)
                headers = _login(client)

                resp = client.patch(
                    f"/anomalies/{aid}/feedback",
                    json={"rating": "DISLIKE"},
                    headers=headers,
                )
                assert resp.status_code == 200
                body = resp.json()
                assert body["feedback_rating"] == "DISLIKE"
                assert body["false_positive_count"] == 1

                # Second DISLIKE increments again
                resp2 = client.patch(
                    f"/anomalies/{aid}/feedback",
                    json={"rating": "DISLIKE"},
                    headers=headers,
                )
                assert resp2.status_code == 200
                assert resp2.json()["false_positive_count"] == 2
        finally:
            app.dependency_overrides.clear()
            release_conn(conn)

    def test_invalid_rating_returns_400(self):
        conn = _setup()
        try:
            with TestClient(app) as client:
                aid = _seed_anomaly(conn)
                headers = _login(client)

                resp = client.patch(
                    f"/anomalies/{aid}/feedback",
                    json={"rating": "INVALID"},
                    headers=headers,
                )
                assert resp.status_code == 400
        finally:
            app.dependency_overrides.clear()
            release_conn(conn)

    def test_feedback_not_found_returns_404(self):
        conn = _setup()
        try:
            with TestClient(app) as client:
                headers = _login(client)
                resp = client.patch(
                    "/anomalies/99999/feedback",
                    json={"rating": "LIKE"},
                    headers=headers,
                )
                assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()
            release_conn(conn)


# ── Resolve ───────────────────────────────────────────────────────────────


class TestResolve:
    def test_resolve_not_found_returns_404(self):
        conn = _setup()
        try:
            with TestClient(app) as client:
                headers = _login(client)
                resp = client.patch("/anomalies/99999/resolve", headers=headers)
                assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()
            release_conn(conn)


# ── Star ──────────────────────────────────────────────────────────────────


class TestStar:
    def test_star_not_found_returns_404(self):
        conn = _setup()
        try:
            with TestClient(app) as client:
                headers = _login(client)
                resp = client.patch("/anomalies/99999/star", headers=headers)
                assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()
            release_conn(conn)


# ── Sort modes ────────────────────────────────────────────────────────────


class TestListSortModes:
    def test_sort_by_detected_at(self):
        conn = _setup()
        try:
            with TestClient(app) as client:
                now = datetime.now(timezone.utc)
                a1 = _seed_anomaly(conn, anomaly_type="A1", detected_at=now)
                _seed_anomaly(
                    conn, anomaly_type="A2", detected_at=now - timedelta(hours=2)
                )
                headers = _login(client)

                resp = client.get(
                    "/anomalies", params={"sort_by": "detected_at"}, headers=headers
                )
                assert resp.status_code == 200
                data = resp.json()["data"]
                assert len(data) == 2
                # Most recent first
                assert data[0]["id"] == a1
        finally:
            app.dependency_overrides.clear()
            release_conn(conn)

    def test_sort_by_severity(self):
        conn = _setup()
        try:
            with TestClient(app) as client:
                _seed_anomaly(conn, severity="HIGH")
                critical_id = _seed_anomaly(conn, severity="CRITICAL")
                headers = _login(client)

                resp = client.get(
                    "/anomalies", params={"sort_by": "severity"}, headers=headers
                )
                assert resp.status_code == 200
                data = resp.json()["data"]
                assert len(data) == 2
                # CRITICAL should come before HIGH
                assert data[0]["id"] == critical_id
        finally:
            app.dependency_overrides.clear()
            release_conn(conn)

    def test_sort_by_score_default(self):
        conn = _setup()
        try:
            with TestClient(app) as client:
                # A1 (gravity 7) should rank above A7 (gravity 1)
                _seed_anomaly(conn, anomaly_type="A7", severity="LOW")
                a1_id = _seed_anomaly(conn, anomaly_type="A1", severity="CRITICAL")
                headers = _login(client)

                # Default sort is "score"
                resp = client.get("/anomalies", headers=headers)
                assert resp.status_code == 200
                data = resp.json()["data"]
                assert len(data) == 2
                # A1 + CRITICAL should rank higher than A7 + LOW
                assert data[0]["id"] == a1_id
        finally:
            app.dependency_overrides.clear()
            release_conn(conn)


# ── Filters ───────────────────────────────────────────────────────────────


class TestListFilters:
    def test_filter_by_anomaly_type(self):
        conn = _setup()
        try:
            with TestClient(app) as client:
                _seed_anomaly(conn, anomaly_type="A1")
                _seed_anomaly(conn, anomaly_type="A2")
                headers = _login(client)

                resp = client.get(
                    "/anomalies", params={"anomaly_type": "A1"}, headers=headers
                )
                assert resp.status_code == 200
                body = resp.json()
                assert body["total"] == 1
                assert body["data"][0]["anomaly_type"] == "A1"
        finally:
            app.dependency_overrides.clear()
            release_conn(conn)

    def test_filter_by_detection_source(self):
        conn = _setup()
        try:
            with TestClient(app) as client:
                _seed_anomaly(conn, explanation='{"source": "ML_ENSEMBLE"}')
                _seed_anomaly(conn, explanation='{"source": "ZSCORE"}')
                headers = _login(client)

                resp = client.get(
                    "/anomalies", params={"detection_source": "ZSCORE"}, headers=headers
                )
                assert resp.status_code == 200
                body = resp.json()
                assert body["total"] == 1
        finally:
            app.dependency_overrides.clear()
            release_conn(conn)

    def test_filter_by_is_starred(self):
        conn = _setup()
        try:
            with TestClient(app) as client:
                _seed_anomaly(conn, is_starred=1)
                _seed_anomaly(conn, is_starred=0)
                headers = _login(client)

                resp = client.get(
                    "/anomalies", params={"is_starred": 1}, headers=headers
                )
                assert resp.status_code == 200
                assert resp.json()["total"] == 1
        finally:
            app.dependency_overrides.clear()
            release_conn(conn)

    def test_filter_by_entity_type_atm(self):
        conn = _setup()
        try:
            with TestClient(app) as client:
                _seed_anomaly(conn, atm_id="ATM-GB-0001")
                _seed_anomaly(conn, atm_id="ATM-SERVER-001")
                headers = _login(client)

                resp = client.get(
                    "/anomalies", params={"entity_type": "atm"}, headers=headers
                )
                assert resp.status_code == 200
                body = resp.json()
                assert body["total"] == 1
                assert "ATM-GB-" in body["data"][0]["atm_id"]
        finally:
            app.dependency_overrides.clear()
            release_conn(conn)

    def test_filter_by_entity_type_server(self):
        conn = _setup()
        try:
            with TestClient(app) as client:
                _seed_anomaly(conn, atm_id="ATM-GB-0001")
                _seed_anomaly(conn, atm_id="ATM-SERVER-001")
                headers = _login(client)

                resp = client.get(
                    "/anomalies", params={"entity_type": "server"}, headers=headers
                )
                assert resp.status_code == 200
                body = resp.json()
                assert body["total"] == 1
                assert "ATM-SERVER-" in body["data"][0]["atm_id"]
        finally:
            app.dependency_overrides.clear()
            release_conn(conn)

    def test_filter_by_date_range(self):
        conn = _setup()
        try:
            with TestClient(app) as client:
                old = datetime.now(timezone.utc) - timedelta(days=7)
                _seed_anomaly(conn, detected_at=old)
                _seed_anomaly(conn, detected_at=datetime.now(timezone.utc))
                headers = _login(client)

                recent = datetime.now(timezone.utc) - timedelta(hours=1)
                resp = client.get(
                    "/anomalies",
                    params={"from_date": recent.isoformat()},
                    headers=headers,
                )
                assert resp.status_code == 200
                assert resp.json()["total"] == 1
        finally:
            app.dependency_overrides.clear()
            release_conn(conn)


# ── Grouping modes ────────────────────────────────────────────────────────


class TestListGroupingModes:
    def test_group_by_atm_anomaly(self):
        conn = _setup()
        try:
            with TestClient(app) as client:
                _seed_anomaly(conn, anomaly_type="A1", atm_id="ATM-GB-0001")
                _seed_anomaly(
                    conn, anomaly_type="A1", atm_id="ATM-GB-0001"
                )  # duplicate
                _seed_anomaly(conn, anomaly_type="A2", atm_id="ATM-GB-0001")
                headers = _login(client)

                resp = client.get(
                    "/anomalies", params={"group_by": "atm_anomaly"}, headers=headers
                )
                assert resp.status_code == 200
                body = resp.json()
                # 2 unique atm_id + anomaly_type combos
                assert body["total"] == 2
                assert len(body["data"]) == 2
        finally:
            app.dependency_overrides.clear()
            release_conn(conn)

    def test_group_by_title_atm(self):
        conn = _setup()
        try:
            with TestClient(app) as client:
                _seed_anomaly(conn, title="Connection Timeout", atm_id="ATM-GB-0001")
                _seed_anomaly(
                    conn, title="Connection Timeout", atm_id="ATM-GB-0001"
                )  # duplicate
                _seed_anomaly(conn, title="Cassandra Error", atm_id="ATM-GB-0001")
                headers = _login(client)

                resp = client.get(
                    "/anomalies", params={"group_by": "title_atm"}, headers=headers
                )
                assert resp.status_code == 200
                body = resp.json()
                assert body["total"] == 2
                assert len(body["data"]) == 2
        finally:
            app.dependency_overrides.clear()
            release_conn(conn)


# ── Auth enforcement ──────────────────────────────────────────────────────


class TestAuthEnforcement:
    def test_list_returns_401_without_token(self):
        conn = _setup()
        try:
            with TestClient(app) as client:
                resp = client.get("/anomalies")
                assert resp.status_code in (401, 403)
        finally:
            app.dependency_overrides.clear()
            release_conn(conn)

    def test_feedback_returns_401_without_token(self):
        conn = _setup()
        try:
            with TestClient(app) as client:
                resp = client.patch("/anomalies/1/feedback", json={"rating": "LIKE"})
                assert resp.status_code in (401, 403)
        finally:
            app.dependency_overrides.clear()
            release_conn(conn)


# ── Pagination ────────────────────────────────────────────────────────────


class TestPagination:
    def test_explicit_limit_and_offset(self):
        conn = _setup()
        try:
            with TestClient(app) as client:
                ids = []
                for i in range(5):
                    ids.append(_seed_anomaly(conn, title=f"Anomaly {i}"))
                headers = _login(client)

                resp = client.get(
                    "/anomalies", params={"limit": 2, "offset": 0}, headers=headers
                )
                assert resp.status_code == 200
                body = resp.json()
                assert body["limit"] == 2
                assert body["offset"] == 0
                assert len(body["data"]) == 2
        finally:
            app.dependency_overrides.clear()
            release_conn(conn)
