from datetime import datetime, timezone

from fastapi.testclient import TestClient
from psycopg2.extras import Json

from backend.src.api.server import app
from backend.src.database.connection import get_conn, release_conn
from backend.src.auth import auth_router
from backend.tests.helpers import reset_test_db


def test_get_analysis():
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
                    (now, "A1", "ATM-1", "HIGH", "TestHigh", '{}', "act", Json(["ATM_APP"]), 1),
                )
                cur.execute(
                    """
                    INSERT INTO anomalies
                    (detected_at, anomaly_type, atm_id, severity, title, explanation, recommended_action, sources_involved, is_active)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (datetime.now(timezone.utc), "A2", "ATM-1", "CRITICAL", "TestCritical", '{}', "act", Json(["ATM_APP"]), 1),
                )
            conn.commit()

            resp = client.post("/auth/login", data={"username": "admin", "password": "admin"})
            assert resp.status_code == 200, resp.text
            token = resp.json()["access_token"]
            headers = {"Authorization": f"Bearer {token}"}

            analysis = client.get("/analysis/detailed", headers=headers)
            assert analysis.status_code == 200
            data = analysis.json()["data"]
            assert len(data) >= 2
    finally:
        app.dependency_overrides.clear()
        release_conn(conn)
