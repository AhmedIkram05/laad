"""Comprehensive tests for admin router endpoints.

Covers ingestion-errors CRUD, cleanup/wipe trigger,
and admin user creation with validation.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

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


def _admin_login(client) -> dict:
    resp = client.post("/auth/login", data={"username": "admin", "password": "admin"})
    assert resp.status_code == 200, resp.text
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _user_login(client, username="normal1", password="password1") -> dict:
    resp = client.post(
        "/auth/register", json={"username": username, "password": password}
    )
    assert resp.status_code == 201
    login = client.post(
        "/auth/login", data={"username": username, "password": password}
    )
    assert login.status_code == 200
    token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ── Ingestion-errors ──────────────────────────────────────────────────────


class TestIngestionErrors:
    def test_get_ingestion_errors_returns_empty(self):
        conn = _setup()
        try:
            with TestClient(app) as client:
                headers = _admin_login(client)
                resp = client.get("/admin/ingestion-errors", headers=headers)
                assert resp.status_code == 200
                body = resp.json()
                assert "total" in body
                assert "data" in body
                assert body["total"] == 0
        finally:
            app.dependency_overrides.clear()
            release_conn(conn)

    def test_get_ingestion_errors_with_data(self):
        conn = _setup()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO ingestion_errors (timestamp, source, error_detail, raw_input) "
                    "VALUES (NOW(), 'INGEST', 'test error', 'raw')"
                )
            conn.commit()

            with TestClient(app) as client:
                headers = _admin_login(client)
                resp = client.get(
                    "/admin/ingestion-errors",
                    params={"limit": 10, "offset": 0},
                    headers=headers,
                )
                assert resp.status_code == 200
                body = resp.json()
                assert body["total"] == 1
                assert len(body["data"]) == 1
                assert body["data"][0]["source"] == "INGEST"
        finally:
            app.dependency_overrides.clear()
            release_conn(conn)

    def test_clear_ingestion_errors(self):
        conn = _setup()
        try:
            with conn.cursor() as cur:
                for i in range(3):
                    cur.execute(
                        "INSERT INTO ingestion_errors (timestamp, source, error_detail) "
                        "VALUES (NOW(), 'INGEST', %s)",
                        (f"error {i}",),
                    )
            conn.commit()

            with TestClient(app) as client:
                headers = _admin_login(client)
                resp = client.delete("/admin/ingestion-errors", headers=headers)
                assert resp.status_code == 200
                assert resp.json()["deleted"] == 3

            # Verify empty
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM ingestion_errors")
                assert cur.fetchone()[0] == 0
        finally:
            app.dependency_overrides.clear()
            release_conn(conn)

    def test_ingestion_errors_requires_admin(self):
        conn = _setup()
        try:
            with TestClient(app) as client:
                headers = _user_login(client)
                resp = client.get("/admin/ingestion-errors", headers=headers)
                assert resp.status_code == 403
        finally:
            app.dependency_overrides.clear()
            release_conn(conn)


# ── Cleanup triggers ──────────────────────────────────────────────────────


class TestCleanupTriggers:
    def test_cleanup_run_returns_dict(self):
        conn = _setup()
        try:
            with TestClient(app) as client:
                headers = _admin_login(client)
                resp = client.post("/admin/cleanup/run", headers=headers)
                assert resp.status_code == 200
                body = resp.json()
                assert "deleted" in body
                assert "retention_days" in body
        finally:
            app.dependency_overrides.clear()
            release_conn(conn)

    def test_cleanup_run_requires_admin(self):
        conn = _setup()
        try:
            with TestClient(app) as client:
                headers = _user_login(client)
                resp = client.post("/admin/cleanup/run", headers=headers)
                assert resp.status_code == 403
        finally:
            app.dependency_overrides.clear()
            release_conn(conn)


# ── Admin create user ─────────────────────────────────────────────────────


class TestAdminCreateUser:
    def test_create_valid_user(self):
        conn = _setup()
        try:
            with TestClient(app) as client:
                headers = _admin_login(client)
                resp = client.post(
                    "/admin/users",
                    json={
                        "username": "newguy",
                        "password": "pass123",
                        "confirm_password": "pass123",
                        "role": "user",
                    },
                    headers=headers,
                )
                assert resp.status_code == 201
                body = resp.json()
                assert body["username"] == "newguy"
                assert body["role"] == "user"
                assert "id" in body
        finally:
            app.dependency_overrides.clear()
            release_conn(conn)

    def test_create_user_password_mismatch(self):
        conn = _setup()
        try:
            with TestClient(app) as client:
                headers = _admin_login(client)
                resp = client.post(
                    "/admin/users",
                    json={
                        "username": "badpwd",
                        "password": "pass123",
                        "confirm_password": "wrong",
                        "role": "user",
                    },
                    headers=headers,
                )
                assert resp.status_code == 400
                assert "passwords do not match" in resp.text.lower()
        finally:
            app.dependency_overrides.clear()
            release_conn(conn)

    def test_create_user_duplicate_username(self):
        conn = _setup()
        try:
            with TestClient(app) as client:
                headers = _admin_login(client)
                # First create
                client.post(
                    "/admin/users",
                    json={
                        "username": "dupuser",
                        "password": "pass123",
                        "confirm_password": "pass123",
                        "role": "user",
                    },
                    headers=headers,
                )
                # Duplicate
                resp = client.post(
                    "/admin/users",
                    json={
                        "username": "dupuser",
                        "password": "pass123",
                        "confirm_password": "pass123",
                        "role": "user",
                    },
                    headers=headers,
                )
                assert resp.status_code == 409
                assert "already exists" in resp.text.lower()
        finally:
            app.dependency_overrides.clear()
            release_conn(conn)

    def test_create_user_invalid_role(self):
        conn = _setup()
        try:
            with TestClient(app) as client:
                headers = _admin_login(client)
                resp = client.post(
                    "/admin/users",
                    json={
                        "username": "badrole",
                        "password": "pass123",
                        "confirm_password": "pass123",
                        "role": "superadmin",
                    },
                    headers=headers,
                )
                assert resp.status_code == 400
                assert "role" in resp.text.lower()
        finally:
            app.dependency_overrides.clear()
            release_conn(conn)
