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


def test_list_atms_status_and_get_not_found(tmp_path):
    tmp_db = tmp_path / "test_atms.db"
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
            # seed two ATMs
            conn.execute("INSERT INTO atms (atm_id, os_version, location_code) VALUES (?, ?, ?)",
                         ("ATM-OK", "v1", "L1"))
            conn.execute("INSERT INTO atms (atm_id, os_version, location_code) VALUES (?, ?, ?)",
                         ("ATM-BAD", "v1", "L2"))

            # Insert anomalies: one CRITICAL for ATM-BAD, one HIGH for ATM-OK
            conn.execute(
                "INSERT INTO anomalies (detected_at, anomaly_type, atm_id, severity, title, explanation, recommended_action, sources_involved, is_active) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                ((datetime.now(timezone.utc).isoformat()), "A1", "ATM-BAD", "CRITICAL", "C", "e", "r", "[\"ATM_APP\"]", 1)
            )
            conn.execute(
                "INSERT INTO anomalies (detected_at, anomaly_type, atm_id, severity, title, explanation, recommended_action, sources_involved, is_active) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                ((datetime.now(timezone.utc).isoformat()), "A2", "ATM-OK", "HIGH", "H", "e", "r", "[\"ATM_APP\"]", 1)
            )
            conn.commit()

            # Login admin
            resp = client.post("/auth/login", data={"username": "admin", "password": "admin"})
            assert resp.status_code == 200, resp.text
            token = resp.json()["access_token"]
            headers = {"Authorization": f"Bearer {token}"}

            # List ATMs and check derived status
            r = client.get("/atms", headers=headers)
            assert r.status_code == 200
            data = r.json()["data"]
            # Find entries
            by_id = {row["atm_id"]: row for row in data}
            assert by_id["ATM-BAD"]["status"] == "CRITICAL"
            assert by_id["ATM-OK"]["status"] in ("WARNING", "CRITICAL", "OK")

            # Get non-existent ATM -> 404
            g = client.get("/atms/NOPE", headers=headers)
            assert g.status_code == 404
    finally:
        conn.close()
        app.dependency_overrides.clear()
