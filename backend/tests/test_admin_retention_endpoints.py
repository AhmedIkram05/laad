from fastapi.testclient import TestClient

from backend.src.api.server import app
from backend.src.database.connection import get_conn, release_conn
from backend.src.auth import auth_router
from backend.tests.helpers import reset_test_db


# Test admin data retention endpoints
def test_admin_retention_get_put_and_permissions():
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
            resp = client.post('/auth/login', data={'username': 'admin', 'password': 'admin'})
            assert resp.status_code == 200, resp.text
            admin_token = resp.json()['access_token']
            admin_headers = {'Authorization': f'Bearer {admin_token}'}

            r = client.get('/admin/retention', headers=admin_headers)
            assert r.status_code == 200
            body = r.json()
            assert 'retention_days' in body and 'updated_at' in body

            p = client.put('/admin/retention', json={'days': 30}, headers=admin_headers)
            assert p.status_code == 200
            assert p.json().get('retention_days') == 30

            bad = client.put('/admin/retention', json={'days': 2}, headers=admin_headers)
            assert bad.status_code == 400

            reg = client.post('/auth/register', json={'username': 'normal1', 'password': 'password1'})
            assert reg.status_code == 201
            login = client.post('/auth/login', data={'username': 'normal1', 'password': 'password1'})
            assert login.status_code == 200
            user_token = login.json()['access_token']
            user_headers = {'Authorization': f'Bearer {user_token}'}

            forbidden = client.put('/admin/retention', json={'days': 7}, headers=user_headers)
            assert forbidden.status_code == 403
    finally:
        app.dependency_overrides.clear()
        release_conn(conn)


# Test admin wipe endpoint
def test_admin_wipe_invokes_run_wipe_and_requires_admin(monkeypatch):
    reset_test_db()
    conn = get_conn()

    def override_get_db():
        try:
            yield conn
        finally:
            pass

    app.dependency_overrides[auth_router.get_db_connection] = override_get_db

    from backend.src.admin import admin_router as admin_router_mod

    invoked = {}

    def fake_run_wipe():
        invoked['called'] = True
        return {'deleted': 0}

    monkeypatch.setattr(admin_router_mod, 'run_wipe', fake_run_wipe)

    try:
        with TestClient(app) as client:
            resp = client.post('/auth/login', data={'username': 'admin', 'password': 'admin'})
            assert resp.status_code == 200
            token = resp.json()['access_token']
            headers = {'Authorization': f'Bearer {token}'}

            r = client.post('/admin/cleanup/wipe', headers=headers)
            assert r.status_code == 200
            assert invoked.get('called') is True

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
        release_conn(conn)
