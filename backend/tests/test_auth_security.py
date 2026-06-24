from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi.testclient import TestClient

from backend.src.api.server import app
from backend.src.database.connection import get_conn, release_conn
from backend.src.auth import auth_router
from backend.tests.helpers import reset_test_db


def test_admin_endpoint_forbidden_for_non_admin():
    reset_test_db()
    conn = get_conn()

    with conn.cursor() as cur:
        pw_hash = bcrypt.hashpw(b"userpass", bcrypt.gensalt()).decode()
        cur.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (%s, %s, %s)",
            ("normaluser", pw_hash, "user"),
        )
    conn.commit()

    def override_get_db():
        try:
            yield conn
        finally:
            pass

    app.dependency_overrides[auth_router.get_db_connection] = override_get_db

    try:
        with TestClient(app) as client:
            r = client.post(
                "/auth/login", data={"username": "normaluser", "password": "userpass"}
            )
            assert r.status_code == 200, r.text
            token = r.json()["access_token"]
            headers = {"Authorization": f"Bearer {token}"}

            r2 = client.get("/admin/retention", headers=headers)
            assert r2.status_code == 403
            assert "Admin access required" in r2.json().get("detail", "")

            r3 = client.post(
                "/auth/login", data={"username": "admin", "password": "admin"}
            )
            assert r3.status_code == 200, r3.text
            admin_headers = {"Authorization": f"Bearer {r3.json()['access_token']}"}
            r4 = client.get("/admin/retention", headers=admin_headers)
            assert r4.status_code == 200
    finally:
        app.dependency_overrides.clear()
        release_conn(conn)


def test_expired_token_returns_401():
    reset_test_db()
    conn = get_conn()

    def override_get_db():
        try:
            yield conn
        finally:
            pass

    app.dependency_overrides[auth_router.get_db_connection] = override_get_db

    try:
        payload = {
            "sub": "admin",
            "role": "admin",
            "exp": datetime.now(timezone.utc) - timedelta(minutes=5),
        }
        token = jwt.encode(
            payload, auth_router.SECRET_KEY, algorithm=auth_router.ALGORITHM
        )

        with TestClient(app) as client:
            r = client.get(
                "/admin/retention", headers={"Authorization": f"Bearer {token}"}
            )
            assert r.status_code == 401
            assert "Session expired" in r.json().get("detail", "")
    finally:
        app.dependency_overrides.clear()
        release_conn(conn)
