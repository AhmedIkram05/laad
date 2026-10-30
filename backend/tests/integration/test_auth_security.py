from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
import pytest
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


# ── Secret key strength (no padding of short secrets) ────────────────────


def test_load_secret_key_rejects_short_secret(monkeypatch):
    """A too-short JWT_SECRET_KEY must fail loudly instead of being padded."""
    monkeypatch.setenv("JWT_SECRET_KEY", "short")
    with pytest.raises(RuntimeError, match="at least 32 bytes"):
        auth_router._load_secret_key()


def test_load_secret_key_rejects_missing_secret(monkeypatch):
    """Missing JWT_SECRET_KEY still raises the original clear error."""
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
    with pytest.raises(RuntimeError, match="required"):
        auth_router._load_secret_key()


def test_load_secret_key_accepts_32_byte_secret(monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", "x" * 32)
    assert auth_router._load_secret_key() == "x" * 32


# ── Login timing: unknown username must match wrong-password path ────────


def test_login_unknown_username_returns_generic_401():
    reset_test_db()
    conn = get_conn()

    def override_get_db():
        try:
            yield conn
        finally:
            pass

    app.dependency_overrides[auth_router.get_db_connection] = override_get_db

    try:
        with TestClient(app) as client:
            r = client.post(
                "/auth/login",
                data={"username": "no_such_user_here", "password": "whatever1"},
            )
            assert r.status_code == 401
            # Same generic detail as the wrong-password path — no enumeration.
            assert r.json()["detail"] == "Invalid username or password"

            r2 = client.post(
                "/auth/login", data={"username": "admin", "password": "wrongpw"}
            )
            assert r2.status_code == 401
            assert r2.json()["detail"] == "Invalid username or password"
    finally:
        app.dependency_overrides.clear()
        release_conn(conn)


def test_dummy_hash_is_bcrypt_format():
    """The burn hash exists and is a real bcrypt digest (for the timing fix)."""
    assert auth_router._DUMMY_HASH.startswith(b"$2b$")


# ── /auth/register admin gate ────────────────────────────────────────────


def test_register_requires_auth_when_registration_closed(monkeypatch):
    reset_test_db()
    conn = get_conn()

    def override_get_db():
        try:
            yield conn
        finally:
            pass

    app.dependency_overrides[auth_router.get_db_connection] = override_get_db
    monkeypatch.delenv("ALLOW_OPEN_REGISTRATION", raising=False)

    try:
        with TestClient(app) as client:
            client.cookies.clear()
            r = client.post(
                "/auth/register", json={"username": "anon1", "password": "secret1"}
            )
            assert r.status_code == 401
    finally:
        app.dependency_overrides.clear()
        release_conn(conn)


def test_register_forbidden_for_non_admin_when_closed(monkeypatch):
    reset_test_db()
    conn = get_conn()

    with conn.cursor() as cur:
        pw_hash = bcrypt.hashpw(b"userpass", bcrypt.gensalt()).decode()
        cur.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (%s, %s, %s)",
            ("gateuser", pw_hash, "user"),
        )
    conn.commit()

    def override_get_db():
        try:
            yield conn
        finally:
            pass

    app.dependency_overrides[auth_router.get_db_connection] = override_get_db
    monkeypatch.delenv("ALLOW_OPEN_REGISTRATION", raising=False)

    try:
        with TestClient(app) as client:
            r = client.post(
                "/auth/login", data={"username": "gateuser", "password": "userpass"}
            )
            assert r.status_code == 200, r.text

            r2 = client.post(
                "/auth/register", json={"username": "gateuser2", "password": "secret1"}
            )
            assert r2.status_code == 403
            assert "Admin access required" in r2.json().get("detail", "")
    finally:
        app.dependency_overrides.clear()
        release_conn(conn)


def test_register_open_when_env_allows(monkeypatch):
    reset_test_db()
    conn = get_conn()

    def override_get_db():
        try:
            yield conn
        finally:
            pass

    app.dependency_overrides[auth_router.get_db_connection] = override_get_db
    monkeypatch.setenv("ALLOW_OPEN_REGISTRATION", "true")

    try:
        with TestClient(app) as client:
            client.cookies.clear()
            r = client.post(
                "/auth/register", json={"username": "openreg1", "password": "secret1"}
            )
            assert r.status_code == 201, r.text
    finally:
        app.dependency_overrides.clear()
        release_conn(conn)


# ── require_admin verifies current role from the DB ──────────────────────


def test_admin_access_revoked_after_role_demotion():
    """A demoted admin's still-valid JWT must lose admin access."""
    reset_test_db()
    conn = get_conn()

    def override_get_db():
        try:
            yield conn
        finally:
            pass

    app.dependency_overrides[auth_router.get_db_connection] = override_get_db

    try:
        with TestClient(app) as client:
            r = client.post(
                "/auth/login", data={"username": "admin", "password": "admin"}
            )
            assert r.status_code == 200, r.text
            headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

            r2 = client.get("/admin/retention", headers=headers)
            assert r2.status_code == 200

            with conn.cursor() as cur:
                cur.execute("UPDATE users SET role = 'user' WHERE username = 'admin'")
            conn.commit()

            r3 = client.get("/admin/retention", headers=headers)
            assert r3.status_code == 403
            assert "Admin access required" in r3.json().get("detail", "")
    finally:
        app.dependency_overrides.clear()
        release_conn(conn)


def test_forged_admin_jwt_rejected_for_unknown_user():
    """A validly-signed JWT claiming admin for a nonexistent user is 403."""
    reset_test_db()
    conn = get_conn()

    def override_get_db():
        try:
            yield conn
        finally:
            pass

    app.dependency_overrides[auth_router.get_db_connection] = override_get_db

    try:
        token = jwt.encode(
            {
                "sub": "ghost_user",
                "role": "admin",
                "exp": datetime.now(timezone.utc) + timedelta(hours=1),
            },
            auth_router.SECRET_KEY,
            algorithm=auth_router.ALGORITHM,
        )
        with TestClient(app) as client:
            r = client.get(
                "/admin/retention", headers={"Authorization": f"Bearer {token}"}
            )
            assert r.status_code == 403
    finally:
        app.dependency_overrides.clear()
        release_conn(conn)
