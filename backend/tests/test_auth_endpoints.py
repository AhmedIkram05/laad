import os

import pytest
import sqlite3
from fastapi.testclient import TestClient

from backend.api.server import app
from backend.database.connection import get_db
import backend.database.init_db as init_db_module
from backend.src.auth import router as auth_router


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

    app.dependency_overrides[auth_router.getDbConnection] = override_get_db

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
