import os
import sqlite3
from datetime import datetime, timezone

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

# Test admin data retention endpoints
def test_admin_retention_get_put_and_permissions(tmp_path):
    tmp_db = tmp_path / "test_admin_retention.db"
    schema_path = os.path.join(os.path.dirname(init_db_module.__file__), "schema.sql")

    init_db_module.init_db(db_path=str(tmp_db), schema_path=str(schema_path))

    conn = _make_conn(tmp_db)

    def override_get_db():
        try:
            yield conn
        finally:
            pass

    app.dependency_overrides[auth_router.get_db_connection] = override_get_db

    try:
        with TestClient(app) as client:
            # Admin login (seeded by init_db)
            resp = client.post('/auth/login', data={'username': 'admin', 'password': 'admin'})
            assert resp.status_code == 200, resp.text
            admin_token = resp.json()['access_token']
            admin_headers = {'Authorization': f'Bearer {admin_token}'}

            # GET retention
            r = client.get('/admin/retention', headers=admin_headers)
            assert r.status_code == 200
            body = r.json()
            assert 'retention_days' in body and 'updated_at' in body

            # PUT valid value
            p = client.put('/admin/retention', json={'days': 30}, headers=admin_headers)
            assert p.status_code == 200
            assert p.json().get('retention_days') == 30

            # PUT invalid value
            bad = client.put('/admin/retention', json={'days': 2}, headers=admin_headers)
            assert bad.status_code == 400

            # Non-admin user cannot update retention
            reg = client.post('/auth/register', json={'username': 'normal1', 'password': 'password1'})
            assert reg.status_code == 201
            login = client.post('/auth/login', data={'username': 'normal1', 'password': 'password1'})
            assert login.status_code == 200
            user_token = login.json()['access_token']
            user_headers = {'Authorization': f'Bearer {user_token}'}

            forbidden = client.put('/admin/retention', json={'days': 7}, headers=user_headers)
            assert forbidden.status_code == 403
    finally:
        conn.close()
        app.dependency_overrides.clear()


# Test admin wipe endpoint
def test_admin_wipe_invokes_run_wipe_and_requires_admin(tmp_path, monkeypatch):
    tmp_db = tmp_path / "test_admin_wipe.db"
    schema_path = os.path.join(os.path.dirname(init_db_module.__file__), "schema.sql")

    init_db_module.init_db(db_path=str(tmp_db), schema_path=str(schema_path))

    conn = _make_conn(tmp_db)

    def override_get_db():
        try:
            yield conn
        finally:
            pass

    app.dependency_overrides[auth_router.get_db_connection] = override_get_db

    # Monkeypatch the admin_router.run_wipe to observe invocation
    from backend.src.admin import admin_router as admin_router_mod

    invoked = {}

    def fake_run_wipe():
        invoked['called'] = True
        return {'deleted': 0}

    monkeypatch.setattr(admin_router_mod, 'run_wipe', fake_run_wipe)

    try:
        with TestClient(app) as client:
            # Admin login
            resp = client.post('/auth/login', data={'username': 'admin', 'password': 'admin'})
            assert resp.status_code == 200
            token = resp.json()['access_token']
            headers = {'Authorization': f'Bearer {token}'}

            r = client.post('/admin/cleanup/wipe', headers=headers)
            assert r.status_code == 200
            assert invoked.get('called') is True

            # Non-admin cannot call
            reg = client.post('/auth/register', json={'username': 'normal2', 'password': 'password2'})
            assert reg.status_code == 201
            login = client.post('/auth/login', data={'username': 'normal2', 'password': 'password2'})
            assert login.status_code == 200
            user_token = login.json()['access_token']
            user_headers = {'Authorization': f'Bearer {user_token}'}

            r2 = client.post('/admin/cleanup/wipe', headers=user_headers)
            assert r2.status_code == 403
    finally:
        app.dependency_overrides.clear()
        conn.close()
