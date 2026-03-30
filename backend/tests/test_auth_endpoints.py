import os

import pytest
import sqlite3
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient

from backend.src.api.server import app
from backend.src.database.connection import get_db
import backend.src.database.init_db as init_db_module
from backend.src.auth import auth_router


@pytest.fixture
def client(tmp_path):
    # Create a temporary database file and initialise schema + seeds
    tmp_db = tmp_path / "test_auth.db"
    schema_path = os.path.join(os.path.dirname(init_db_module.__file__), "schema.sql")

    # Initialise DB (pass absolute paths so init_db uses them directly)
    init_db_module.init_db(db_path=str(tmp_db), schema_path=str(schema_path))

    # Open a persistent connection for the TestClient dependency override
    # Use check_same_thread=False so the TestClient's worker threads can use it.
    conn = sqlite3.connect(str(tmp_db), timeout=5.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("PRAGMA foreign_keys = ON")

    def override_get_db():
        try:
            yield conn
        finally:
            pass

    app.dependency_overrides[auth_router.get_db_connection] = override_get_db

    with TestClient(app) as c:
        yield c

    conn.close()
    app.dependency_overrides.clear()


def test_admin_login_and_me(client):
    # Login as seeded admin
    resp = client.post("/auth/login", data={"username": "admin", "password": "admin"})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["role"] == "admin"
    assert "access_token" in data

    token = data["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    me = client.get("/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["username"] == "admin"
    assert me.json()["role"] == "admin"


def test_otp_generate_redeem_and_guests(client):
    # Admin login
    resp = client.post("/auth/login", data={"username": "admin", "password": "admin"})
    assert resp.status_code == 200
    admin_token = resp.json()["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    # Generate a user OTP
    gen = client.post("/auth/otp/generate", json={"role": "user"}, headers=admin_headers)
    assert gen.status_code == 200, gen.text
    otp = gen.json()["token"]

    # Redeem the OTP
    redeem = client.post("/auth/otp/redeem", params={"token": otp})
    assert redeem.status_code == 200, redeem.text
    guest_token = redeem.json()["access_token"]
    assert redeem.json()["role"] == "user"

    # Redeeming again should return 410
    redeem_again = client.post("/auth/otp/redeem", params={"token": otp})
    assert redeem_again.status_code == 410

    # Guest must not be able to generate OTPs (admin-only)
    guest_headers = {"Authorization": f"Bearer {guest_token}"}
    forbidden = client.post("/auth/otp/generate", json={"role": "user"}, headers=guest_headers)
    assert forbidden.status_code == 403


@pytest.fixture
def client_and_conn(tmp_path):
    tmp_db = tmp_path / "test_auth_additional.db"
    schema_path = os.path.join(os.path.dirname(init_db_module.__file__), "schema.sql")

    init_db_module.init_db(db_path=str(tmp_db), schema_path=str(schema_path))

    conn = sqlite3.connect(str(tmp_db), timeout=5.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("PRAGMA foreign_keys = ON")

    def override_get_db():
        try:
            yield conn
        finally:
            pass

    app.dependency_overrides[auth_router.get_db_connection] = override_get_db

    with TestClient(app) as c:
        yield c, conn

    conn.close()
    app.dependency_overrides.clear()


def test_invalid_credentials(client_and_conn):
    client, _ = client_and_conn
    resp = client.post("/auth/login", data={"username": "admin", "password": "wrong"})
    assert resp.status_code == 401


def test_missing_and_malformed_token(client_and_conn):
    client, _ = client_and_conn
    # Missing token
    r = client.get("/auth/me")
    assert r.status_code == 401

    # Malformed token
    r2 = client.get("/auth/me", headers={"Authorization": "Bearer not_a_jwt"})
    assert r2.status_code == 401


def test_generate_invalid_role_and_nonexistent_redeem(client_and_conn):
    client, conn = client_and_conn
    # Login admin
    resp = client.post("/auth/login", data={"username": "admin", "password": "admin"})
    assert resp.status_code == 200
    admin_token = resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {admin_token}"}

    # Invalid role
    gen = client.post("/auth/otp/generate", json={"role": "invalid_role"}, headers=headers)
    assert gen.status_code == 400

    # Redeem nonexistent token
    redeem = client.post("/auth/otp/redeem", params={"token": "nope"})
    assert redeem.status_code == 404


def test_redeem_expired_and_used_token_and_created_by(client_and_conn):
    client, conn = client_and_conn
    # Login admin
    resp = client.post("/auth/login", data={"username": "admin", "password": "admin"})
    admin_token = resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {admin_token}"}

    # Generate a token (valid)
    gen = client.post("/auth/otp/generate", json={"role": "user"}, headers=headers)
    assert gen.status_code == 200
    token = gen.json()["token"]

    # Force-create an expired token
    expired = "expiredtok123"
    past = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
    conn.execute(
        "INSERT INTO otp_tokens (token, role, created_by, created_at, expires_at) VALUES (?, ?, ?, ?, ?)",
        (expired, "user", 1, datetime.now(timezone.utc).isoformat(), past)
    )
    conn.commit()

    r = client.post("/auth/otp/redeem", params={"token": expired})
    assert r.status_code == 410

    # Force-create a used token
    used = "usedtok123"
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO otp_tokens (token, role, created_by, created_at, expires_at, used_at) VALUES (?, ?, ?, ?, ?, ?)",
        (used, "user", 1, now, (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat(), now)
    )
    conn.commit()

    r2 = client.post("/auth/otp/redeem", params={"token": used})
    assert r2.status_code == 410

    # Ensure the generated token has created_by populated (admin id exists)
    # We previously generated `token` via the API; fetch it
    row = conn.execute("SELECT created_by FROM otp_tokens WHERE token = ?", (token,)).fetchone()
    assert row is not None
    assert row["created_by"] is not None


def test_register_success(client_and_conn):
    client, conn = client_and_conn
    resp = client.post("/auth/register", json={"username": "newuser", "password": "secret123"})
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["username"] == "newuser"

    # Verify DB row created and default role applied
    row = conn.execute("SELECT username, role FROM users WHERE username = ?", ("newuser",)).fetchone()
    assert row is not None
    assert row["username"] == "newuser"
    assert row["role"] == "user"


def test_register_duplicate_username(client_and_conn):
    client, _ = client_and_conn
    # 'admin' is seeded by init_db
    resp = client.post("/auth/register", json={"username": "admin", "password": "whatever"})
    assert resp.status_code == 409


def test_register_bad_payload(client_and_conn):
    client, _ = client_and_conn
    # Missing password (Pydantic will return 422 for missing required fields)
    resp = client.post("/auth/register", json={"username": "useronly"})
    assert resp.status_code == 422

    # Short password
    resp2 = client.post("/auth/register", json={"username": "u2", "password": "123"})
    assert resp2.status_code == 400





def test_admin_create_user_endpoint(client_and_conn):
    client, conn = client_and_conn
    # Login admin
    resp = client.post("/auth/login", data={"username": "admin", "password": "admin"})
    assert resp.status_code == 200
    admin_token = resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {admin_token}"}

    # Create a new admin via admin endpoint
    r = client.post("/admin/users", json={"username": "created_admin", "password": "adminpass", "role": "admin"}, headers=headers)
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["username"] == "created_admin"
    assert data["role"] == "admin"

    # Non-admin cannot create
    # First login as a normal user
    client.post("/auth/register", json={"username": "plainuser", "password": "pass123"})
    resp2 = client.post("/auth/login", data={"username": "plainuser", "password": "pass123"})
    assert resp2.status_code == 200
    user_token = resp2.json()["access_token"]
    headers_user = {"Authorization": f"Bearer {user_token}"}

    forbidden = client.post("/admin/users", json={"username": "nope", "password": "x", "role": "user"}, headers=headers_user)
    assert forbidden.status_code == 403
