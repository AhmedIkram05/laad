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
