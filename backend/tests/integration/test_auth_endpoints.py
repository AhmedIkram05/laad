import pytest
from fastapi.testclient import TestClient

from backend.src.api.server import app
from backend.src.database.connection import get_conn, release_conn
from backend.src.auth import auth_router
from backend.tests.helpers import reset_test_db


@pytest.fixture
def client_and_conn():
    reset_test_db()
    conn = get_conn()

    def override_get_db():
        try:
            yield conn
        finally:
            pass

    app.dependency_overrides[auth_router.get_db_connection] = override_get_db

    with TestClient(app) as client:
        yield client, conn

    app.dependency_overrides.clear()
    release_conn(conn)


def test_admin_login_and_me(client_and_conn):
    client, _ = client_and_conn
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


def test_invalid_credentials(client_and_conn):
    client, _ = client_and_conn
    resp = client.post("/auth/login", data={"username": "admin", "password": "wrong"})
    assert resp.status_code == 401


def test_missing_and_malformed_token(client_and_conn):
    client, _ = client_and_conn
    r = client.get("/auth/me")
    assert r.status_code == 401

    r2 = client.get("/auth/me", headers={"Authorization": "Bearer not_a_jwt"})
    assert r2.status_code == 401


def test_register_success(client_and_conn):
    client, conn = client_and_conn
    resp = client.post(
        "/auth/register", json={"username": "newuser", "password": "secret123"}
    )
    assert resp.status_code == 201, resp.text

    with conn.cursor() as cur:
        cur.execute(
            "SELECT username, role FROM users WHERE username = %s", ("newuser",)
        )
        row = cur.fetchone()

    assert row is not None
    assert row[0] == "newuser"
    assert row[1] == "user"


def test_register_duplicate_username(client_and_conn):
    client, _ = client_and_conn
    resp = client.post(
        "/auth/register", json={"username": "admin", "password": "whatever"}
    )
    assert resp.status_code == 409


def test_register_bad_payload(client_and_conn):
    client, _ = client_and_conn
    resp = client.post("/auth/register", json={"username": "useronly"})
    assert resp.status_code == 422

    resp2 = client.post("/auth/register", json={"username": "u2", "password": "123"})
    assert resp2.status_code == 400


def test_admin_create_user_endpoint(client_and_conn):
    client, _ = client_and_conn

    resp = client.post("/auth/login", data={"username": "admin", "password": "admin"})
    assert resp.status_code == 200
    admin_token = resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {admin_token}"}

    r = client.post(
        "/admin/users",
        json={
            "username": "created_admin",
            "password": "adminpass",
            "confirm_password": "adminpass",
            "role": "admin",
        },
        headers=headers,
    )
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["username"] == "created_admin"
    assert data["role"] == "admin"

    client.post("/auth/register", json={"username": "plainuser", "password": "pass123"})
    resp2 = client.post(
        "/auth/login", data={"username": "plainuser", "password": "pass123"}
    )
    assert resp2.status_code == 200
    user_token = resp2.json()["access_token"]
    headers_user = {"Authorization": f"Bearer {user_token}"}

    forbidden = client.post(
        "/admin/users",
        json={
            "username": "nope",
            "password": "x",
            "confirm_password": "x",
            "role": "user",
        },
        headers=headers_user,
    )
    assert forbidden.status_code == 403
