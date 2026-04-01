"""Authentication and authorization tests.

Test cases:
- `test_admin_endpoint_forbidden_for_non_admin`: ensures a non-admin user
    receives HTTP 403 when accessing admin-only endpoints and that the seeded
    `admin` user can access them.
- `test_expired_token_returns_401`: crafts an expired JWT and verifies the
    server rejects it with HTTP 401 (session expired).
"""

import os
import sqlite3
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from backend.src.api.server import app
import backend.src.database.init_db as init_db_module
from backend.src.auth import auth_router


def _make_conn(tmp_db_path):
    conn = sqlite3.connect(str(tmp_db_path), timeout=5.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def test_admin_endpoint_forbidden_for_non_admin(tmp_path):
    tmp_db = tmp_path / "test_auth.db"
    schema_path = os.path.join(os.path.dirname(init_db_module.__file__), "schema.sql")

    # initialize schema + seed default admin
    assert init_db_module.init_db(db_path=str(tmp_db), schema_path=str(schema_path)) is True

    conn = _make_conn(tmp_db)

    # create a normal (non-admin) user directly
    try:
        import bcrypt
    except Exception:
        pytest = __import__('pytest')
        pytest.skip("bcrypt required for this test")

    password = "userpass"
    pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    conn.execute("INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)", ("normaluser", pw_hash, "user"))
    conn.commit()

    def override_get_db():
        try:
            yield conn
        finally:
            pass

    app.dependency_overrides[auth_router.get_db_connection] = override_get_db

    try:
        with TestClient(app) as client:
            # login as non-admin
            r = client.post("/auth/login", data={"username": "normaluser", "password": password})
            assert r.status_code == 200, r.text
            token = r.json()["access_token"]
            headers = {"Authorization": f"Bearer {token}"}

            # attempt to access admin-only endpoint
            r2 = client.get("/admin/retention", headers=headers)
            assert r2.status_code == 403
            assert "Admin access required" in r2.json().get("detail", "")

            # admin user should succeed
            r3 = client.post("/auth/login", data={"username": "admin", "password": "admin"})
            assert r3.status_code == 200, r3.text
            admin_token = r3.json()["access_token"]
            admin_headers = {"Authorization": f"Bearer {admin_token}"}
            r4 = client.get("/admin/retention", headers=admin_headers)
            assert r4.status_code == 200
    finally:
        try:
            conn.close()
        except Exception:
            pass
        app.dependency_overrides.clear()


def test_expired_token_returns_401(tmp_path):
    tmp_db = tmp_path / "test_auth_expired.db"
    schema_path = os.path.join(os.path.dirname(init_db_module.__file__), "schema.sql")
    assert init_db_module.init_db(db_path=str(tmp_db), schema_path=str(schema_path)) is True

    conn = _make_conn(tmp_db)

    def override_get_db():
        try:
            yield conn
        finally:
            pass

    app.dependency_overrides[auth_router.get_db_connection] = override_get_db

    try:
        import jwt

        # craft an expired token (exp in the past)
        payload = {"sub": "admin", "role": "admin", "exp": (datetime.now(timezone.utc) - timedelta(minutes=5))}
        token = jwt.encode(payload, auth_router.SECRET_KEY, algorithm=auth_router.ALGORITHM)

        with TestClient(app) as client:
            r = client.get("/admin/retention", headers={"Authorization": f"Bearer {token}"})
            assert r.status_code == 401
            assert "Session expired" in r.json().get("detail", "")
    finally:
        try:
            conn.close()
        except Exception:
            pass
        app.dependency_overrides.clear()
