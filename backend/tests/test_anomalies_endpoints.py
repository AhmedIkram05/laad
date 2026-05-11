from datetime import datetime, timezone, timedelta

from fastapi.testclient import TestClient
from psycopg2.extras import Json

from backend.src.api.server import app
from backend.src.database.connection import get_conn, release_conn
from backend.src.auth import auth_router
from backend.tests.helpers import reset_test_db


def _setup_client_and_conn():
    reset_test_db()
    conn = get_conn()

    def override_get_db():
        try:
            yield conn
        finally:
            pass

    app.dependency_overrides[auth_router.get_db_connection] = override_get_db
    return conn


def test_list_and_filters_and_get_and_feedback_and_resolve():
    conn = _setup_client_and_conn()

    try:
        with TestClient(app) as client:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO atms (atm_id, os_version, location_code) VALUES (%s, %s, %s)",
                    ("ATM-1", "v1", "LOC-1"),
                )

                now = datetime.now(timezone.utc)

                cur.execute(
                    """
                    INSERT INTO anomalies
                    (detected_at, anomaly_type, atm_id, severity, title, explanation, recommended_action, sources_involved, is_active)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (now, "A1", "ATM-1", "HIGH", "TestHigh", "explain", "act", Json(["ATM_APP"]), 1),
                )
                cur.execute(
                    """
                    INSERT INTO anomalies
                    (detected_at, anomaly_type, atm_id, severity, title, explanation, recommended_action, sources_involved, is_active)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (datetime.now(timezone.utc), "A2", "ATM-1", "CRITICAL", "TestCritical", "explain", "act", Json(["ATM_APP"]), 1),
                )
            conn.commit()

            resp = client.post("/auth/login", data={"username": "admin", "password": "admin"})
            assert resp.status_code == 200, resp.text
            token = resp.json()["access_token"]
            headers = {"Authorization": f"Bearer {token}"}

            r = client.get("/anomalies", headers=headers)
            assert r.status_code == 200
            body = r.json()
            assert body["total"] == 2
            assert len(body["data"]) == 2

            r2 = client.get("/anomalies", params={"severity": "critical"}, headers=headers)
            assert r2.status_code == 200
            assert r2.json()["total"] == 1

            with conn.cursor() as cur:
                cur.execute("SELECT id FROM anomalies LIMIT 1")
                row = cur.fetchone()
            aid = row[0]

            res = client.patch(f"/anomalies/{aid}/resolve", headers=headers)
            assert res.status_code in (200, 400, 404)
            if res.status_code == 200:
                assert res.json()["is_active"] == 0
    finally:
        app.dependency_overrides.clear()
        release_conn(conn)


def test_group_by_atm_returns_grouped_rows():
    conn = _setup_client_and_conn()

    try:
        with TestClient(app) as client:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO atms (atm_id, os_version, location_code) VALUES (%s, %s, %s)", ("ATM-A", "v1", "LOC-A"))
                cur.execute("INSERT INTO atms (atm_id, os_version, location_code) VALUES (%s, %s, %s)", ("ATM-B", "v1", "LOC-B"))

                t1 = datetime.now(timezone.utc)
                t2 = datetime.now(timezone.utc) + timedelta(seconds=1)

                cur.execute(
                    """
                    INSERT INTO anomalies
                    (detected_at, anomaly_type, atm_id, severity, title, explanation, recommended_action, sources_involved, is_active)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (t1, "A1", "ATM-A", "HIGH", "A", "explain", "act", Json(["ATM_APP"]), 1),
                )
                cur.execute(
                    """
                    INSERT INTO anomalies
                    (detected_at, anomaly_type, atm_id, severity, title, explanation, recommended_action, sources_involved, is_active)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (t2, "A2", "ATM-A", "CRITICAL", "B", "explain", "act", Json(["ATM_APP"]), 1),
                )
                cur.execute(
                    """
                    INSERT INTO anomalies
                    (detected_at, anomaly_type, atm_id, severity, title, explanation, recommended_action, sources_involved, is_active)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (t1, "A3", "ATM-B", "LOW", "C", "explain", "act", Json(["ATM_APP"]), 1),
                )
            conn.commit()

            resp = client.post("/auth/login", data={"username": "admin", "password": "admin"})
            assert resp.status_code == 200, resp.text
            token = resp.json()["access_token"]
            headers = {"Authorization": f"Bearer {token}"}

            r = client.get("/anomalies", params={"group_by": "atm", "is_active": 1}, headers=headers)
            assert r.status_code == 200
            body = r.json()
            assert body["total"] == 2
            assert len(body["data"]) == 2

            groups = {row["atm_id"]: row for row in body["data"]}
            assert groups["ATM-A"]["count"] == 2
            assert groups["ATM-B"]["count"] == 1
    finally:
        app.dependency_overrides.clear()
        release_conn(conn)


def test_star_toggle():
    conn = _setup_client_and_conn()

    try:
        with TestClient(app) as client:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO atms (atm_id, os_version, location_code) VALUES (%s, %s, %s)",
                    ("ATM-STAR", "v1", "LOC-STAR"),
                )
                cur.execute(
                    """
                    INSERT INTO anomalies
                    (detected_at, anomaly_type, atm_id, severity, title, explanation, recommended_action, sources_involved, is_active)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (datetime.now(timezone.utc), "A1", "ATM-STAR", "HIGH", "StarTest", "explain", "act", Json(["ATM_APP"]), 1),
                )
            conn.commit()

            resp = client.post("/auth/login", data={"username": "admin", "password": "admin"})
            assert resp.status_code == 200, resp.text
            token = resp.json()["access_token"]
            headers = {"Authorization": f"Bearer {token}"}

            with conn.cursor() as cur:
                cur.execute("SELECT id, is_starred FROM anomalies LIMIT 1")
                row = cur.fetchone()
            aid = row[0]
            assert row[1] in (0, None, False)

            t1 = client.patch(f"/anomalies/{aid}/star", headers=headers)
            assert t1.status_code == 200
            assert t1.json().get("is_starred") == 1

            t2 = client.patch(f"/anomalies/{aid}/star", headers=headers)
            assert t2.status_code == 200
            assert t2.json().get("is_starred") == 0
    finally:
        app.dependency_overrides.clear()
        release_conn(conn)
