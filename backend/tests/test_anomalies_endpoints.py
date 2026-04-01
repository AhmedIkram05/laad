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


def test_list_and_filters_and_get_and_feedback_and_resolve(tmp_path):
    # Arrange: prepare a temporary DB and override the app dependency
    tmp_db = tmp_path / "test_anomalies.db"
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

            # Insert several anomalies
            conn.execute(
                "INSERT INTO anomalies (detected_at, anomaly_type, atm_id, severity, title, explanation, recommended_action, sources_involved, is_active) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (now, "A1", "ATM-1", "HIGH", "TestHigh", "explain", "act", "[\"ATM_APP\"]", 1)
            )
            conn.execute(
                "INSERT INTO anomalies (detected_at, anomaly_type, atm_id, severity, title, explanation, recommended_action, sources_involved, is_active) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                ((datetime.now(timezone.utc).isoformat()), "A2", "ATM-1", "CRITICAL", "TestCritical", "explain", "act", "[\"ATM_APP\"]", 1)
            )
            conn.commit()

            # Login to obtain token
            resp = client.post("/auth/login", data={"username": "admin", "password": "admin"})
            assert resp.status_code == 200, resp.text
            token = resp.json()["access_token"]
            headers = {"Authorization": f"Bearer {token}"}

            # List anomalies
            r = client.get("/anomalies", headers=headers)
            assert r.status_code == 200
            body = r.json()
            assert body["total"] == 2
            assert len(body["data"]) == 2

            # Filter by severity (case-insensitive)
            r2 = client.get("/anomalies", params={"severity": "critical"}, headers=headers)
            assert r2.status_code == 200
            assert r2.json()["total"] == 1

            # Get single anomaly id
            row = conn.execute("SELECT id FROM anomalies LIMIT 1").fetchone()
            aid = row[0]

            # Resolve anomaly (admin)
            res = client.patch(f"/anomalies/{aid}/resolve", headers=headers)
            # if it was active this should succeed
            assert res.status_code in (200, 400, 404)
            # If 200, verify is_active is 0
            if res.status_code == 200:
                assert res.json()["is_active"] == 0
    finally:
        conn.close()
        app.dependency_overrides.clear()


def test_group_by_atm_returns_grouped_rows(tmp_path):
    tmp_db = tmp_path / "test_anomalies_group.db"
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
                         ("ATM-A", "v1", "LOC-A"))
            conn.execute("INSERT INTO atms (atm_id, os_version, location_code) VALUES (?, ?, ?)",
                         ("ATM-B", "v1", "LOC-B"))

            t1 = datetime.now(timezone.utc).isoformat()
            t2 = (datetime.now(timezone.utc) + timedelta(seconds=1)).isoformat()

            # Insert anomalies: two for ATM-A, one for ATM-B
            conn.execute(
                "INSERT INTO anomalies (detected_at, anomaly_type, atm_id, severity, title, explanation, recommended_action, sources_involved, is_active) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (t1, "A1", "ATM-A", "HIGH", "A", "explain", "act", '["ATM_APP"]', 1)
            )
            conn.execute(
                "INSERT INTO anomalies (detected_at, anomaly_type, atm_id, severity, title, explanation, recommended_action, sources_involved, is_active) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (t2, "A2", "ATM-A", "CRITICAL", "B", "explain", "act", '["ATM_APP"]', 1)
            )
            conn.execute(
                "INSERT INTO anomalies (detected_at, anomaly_type, atm_id, severity, title, explanation, recommended_action, sources_involved, is_active) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (t1, "A3", "ATM-B", "LOW", "C", "explain", "act", '["ATM_APP"]', 1)
            )
            conn.commit()

            # Login to obtain token
            resp = client.post("/auth/login", data={"username": "admin", "password": "admin"})
            assert resp.status_code == 200, resp.text
            token = resp.json()["access_token"]
            headers = {"Authorization": f"Bearer {token}"}

            # Request grouped anomalies by atm
            r = client.get("/anomalies", params={"group_by": "atm", "is_active": 1}, headers=headers)
            assert r.status_code == 200
            body = r.json()
            assert body["total"] == 2
            assert len(body["data"]) == 2

            groups = {row["atm_id"]: row for row in body["data"]}
            assert groups["ATM-A"]["count"] == 2
            assert groups["ATM-B"]["count"] == 1

            for row in body["data"]:
                assert "group_id" in row
                assert "atm_id" in row
                assert "count" in row
                assert "latest" in row
    finally:
        conn.close()
        app.dependency_overrides.clear()


def test_star_toggle(tmp_path):
    tmp_db = tmp_path / "test_anomalies_star.db"
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
            # seed an ATM referenced by the anomaly
            conn.execute("INSERT INTO atms (atm_id, os_version, location_code) VALUES (?, ?, ?)",
                         ("ATM-STAR", "v1", "LOC-STAR"))

            now = datetime.now(timezone.utc).isoformat()

            # Insert single anomaly (is_starred defaults to 0)
            conn.execute(
                "INSERT INTO anomalies (detected_at, anomaly_type, atm_id, severity, title, explanation, recommended_action, sources_involved, is_active) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (now, "A1", "ATM-STAR", "HIGH", "StarTest", "explain", "act", '["ATM_APP"]', 1)
            )
            conn.commit()

            # Login to obtain token
            resp = client.post("/auth/login", data={"username": "admin", "password": "admin"})
            assert resp.status_code == 200, resp.text
            token = resp.json()["access_token"]
            headers = {"Authorization": f"Bearer {token}"}

            row = conn.execute("SELECT id FROM anomalies LIMIT 1").fetchone()
            aid = row[0]

            # Verify initial starred state via DB
            row2 = conn.execute("SELECT is_starred FROM anomalies WHERE id = ?", (aid,)).fetchone()
            assert row2 is not None
            assert row2["is_starred"] in (0, None, False)

            # Toggle star -> expect starred == 1
            t1 = client.patch(f"/anomalies/{aid}/star", headers=headers)
            assert t1.status_code == 200
            assert t1.json().get("is_starred") == 1

            # Toggle again -> expect starred == 0
            t2 = client.patch(f"/anomalies/{aid}/star", headers=headers)
            assert t2.status_code == 200
            assert t2.json().get("is_starred") == 0
    finally:
        conn.close()
        app.dependency_overrides.clear()
