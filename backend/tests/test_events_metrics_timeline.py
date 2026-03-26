import os
import sqlite3
from datetime import datetime, timezone, timedelta

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


def test_events_list_filters_and_validation(tmp_path):
    tmp_db = tmp_path / "test_events.db"
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
            # Insert two events with different timestamps
            t1 = datetime.now(timezone.utc).isoformat()
            t2 = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()

            payload1 = '{"correlation_id": "corr-1", "location_code": "LOC-1"}'
            payload2 = '{"correlation_id": "corr-2", "location_code": "LOC-2"}'

            conn.execute(
                "INSERT INTO events (timestamp, source, atm_id, correlation_id, transaction_id, event_type, severity, message, payload) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (t1, "ATM_APP", "ATM-1", "corr-1", "tx-1", "TRANSACTION_END", "ERROR", "msg1", payload1)
            )
            conn.execute(
                "INSERT INTO events (timestamp, source, atm_id, correlation_id, transaction_id, event_type, severity, message, payload) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (t2, "TERMINAL_HANDLER", "ATM-2", "corr-2", "tx-2", "TIMEOUT", "INFO", "msg2", payload2)
            )
            conn.commit()

            # Login
            resp = client.post("/auth/login", data={"username": "admin", "password": "admin"})
            assert resp.status_code == 200, resp.text
            token = resp.json()["access_token"]
            headers = {"Authorization": f"Bearer {token}"}

            # Basic list
            r = client.get("/events", headers=headers)
            assert r.status_code == 200
            assert r.json()["total"] == 2

            # Filter by atm_id
            r2 = client.get("/events", params={"atm_id": "ATM-1"}, headers=headers)
            assert r2.status_code == 200
            assert r2.json()["total"] == 1

            # Filter by source (case-insensitive)
            r3 = client.get("/events", params={"source": "atm_app"}, headers=headers)
            assert r3.status_code == 200
            assert r3.json()["total"] == 1

            # Validation: limit > 500 should return 422
            r4 = client.get("/events", params={"limit": 501}, headers=headers)
            assert r4.status_code == 422
    finally:
        conn.close()
        app.dependency_overrides.clear()


def test_metrics_list_filters_and_pagination(tmp_path):
    tmp_db = tmp_path / "test_metrics.db"
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
            t1 = datetime.now(timezone.utc).isoformat()
            payload = '{"component":"cpu"}'

            conn.execute(
                "INSERT INTO metrics (timestamp, source, entity_id, metric_name, metric_value, payload) VALUES (?, ?, ?, ?, ?, ?)",
                (t1, "OS", "ATM-1", "cpu_usage_percent", 42.5, payload)
            )
            conn.commit()

            resp = client.post("/auth/login", data={"username": "admin", "password": "admin"})
            assert resp.status_code == 200, resp.text
            token = resp.json()["access_token"]
            headers = {"Authorization": f"Bearer {token}"}

            r = client.get("/metrics", headers=headers)
            assert r.status_code == 200
            assert r.json()["total"] == 1

            # Filter by metric_name
            r2 = client.get("/metrics", params={"metric_name": "cpu_usage_percent"}, headers=headers)
            assert r2.status_code == 200
            assert r2.json()["total"] == 1
    finally:
        conn.close()
        app.dependency_overrides.clear()


def test_timeline_unified_ordering(tmp_path):
    tmp_db = tmp_path / "test_timeline.db"
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
            # Insert one metric (earlier) and one event (later)
            t_early = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
            t_late = datetime.now(timezone.utc).isoformat()

            conn.execute(
                "INSERT INTO metrics (timestamp, source, entity_id, metric_name, metric_value, payload) VALUES (?, ?, ?, ?, ?, ?)",
                (t_early, "OS", "ATM-1", "mem_used", 128.0, '{"component":"mem"}')
            )
            conn.execute(
                "INSERT INTO events (timestamp, source, atm_id, correlation_id, transaction_id, event_type, severity, message, payload) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (t_late, "ATM_APP", "ATM-1", "corr-1", "tx-1", "EVENT", "INFO", "m", '{"component":"app"}')
            )
            conn.commit()

            resp = client.post("/auth/login", data={"username": "admin", "password": "admin"})
            assert resp.status_code == 200, resp.text
            token = resp.json()["access_token"]
            headers = {"Authorization": f"Bearer {token}"}

            r = client.get("/timeline", headers=headers)
            assert r.status_code == 200
            body = r.json()
            assert body["total"] == 2
            data = body["data"]
            # Ordered by timestamp DESC: first entry should have later timestamp
            assert data[0]["timestamp"] >= data[1]["timestamp"]
    finally:
        conn.close()
        app.dependency_overrides.clear()
