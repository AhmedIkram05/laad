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

def test_get_analysis(tmp_path):
    tmp_db = tmp_path / "test_analysis.db"
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
            # seed an ATM referenced by anomalies
            conn.execute("INSERT INTO atms (atm_id, os_version, location_code) VALUES (?, ?, ?)",
                         ("ATM-1", "v1", "LOC-1"))

            now = datetime.now(timezone.utc).isoformat()

            conn.execute(
                "INSERT INTO anomalies (detected_at, anomaly_type, atm_id, severity, title, explanation, recommended_action, sources_involved, is_active) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (now, "A1", "ATM-1", "HIGH", "TestHigh", "explain", "act", "[\"ATM_APP\"]", 1)
            )
            conn.execute(
                "INSERT INTO anomalies (detected_at, anomaly_type, atm_id, severity, title, explanation, recommended_action, sources_involved, is_active) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                ((datetime.now(timezone.utc).isoformat()), "A2", "ATM-1", "CRITICAL", "TestCritical", "explain", "act", "[\"ATM_APP\"]", 1)
            )
            conn.commit()

            # login
            resp = client.post("/auth/login", data={"username": "admin", "password": "admin"})
            assert resp.status_code == 200, resp.text
            token = resp.json()["access_token"]
            headers = {"Authorization": f"Bearer {token}"}

            # analysis
            a = client.get("/analysis", headers=headers)
            assert a.status_code == 200
            assert len(a) == 2
            data = a.json()["data"]


            
    finally:
        conn.close()
        app.dependency_overrides.clear()