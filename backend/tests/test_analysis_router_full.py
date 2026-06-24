"""Integration tests for /analysis endpoints via TestClient.

Complements test_analysis_endpoints.py (existing /analysis/detailed test) and
test_analysis_metrics.py (unit tests for helper functions) by testing the
/analysis/metrics endpoint with real DB queries through the FastAPI router.
"""

from datetime import datetime, timezone

from fastapi.testclient import TestClient
from psycopg2.extras import Json

from backend.src.database.connection import get_conn, release_conn
from backend.tests.helpers import reset_test_db


def seed_anomaly_data(conn):
    """Insert test anomaly rows for metrics endpoint testing."""
    with conn.cursor() as cur:
        now = datetime.now(timezone.utc)
        anomalies = [
            (now, "A1", "ATM-1", "CRITICAL", "Test Critical", "{}", "action1", 1),
            (now, "A2", "ATM-1", "HIGH", "Test High", "{}", "action2", 1),
            (now, "A3", "ATM-2", "WARNING", "Test Warning", "{}", "action3", 0),
        ]
        for a in anomalies:
            cur.execute(
                """
                INSERT INTO anomalies
                (detected_at, anomaly_type, atm_id, severity, title,
                 explanation, recommended_action, is_active)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                a,
            )
    conn.commit()


class TestAnalysisDetailedEndpoint:
    """Tests for GET /analysis/detailed."""

    def test_detailed_with_data(self):
        reset_test_db()
        conn = get_conn()
        try:
            seed_anomaly_data(conn)
            from backend.src.api.server import app

            with TestClient(app) as client:
                resp = client.get("/analysis/detailed")
                assert resp.status_code == 200
                data = resp.json()
                assert "data" in data
        finally:
            release_conn(conn)

    def test_detailed_with_no_data(self):
        reset_test_db()
        from backend.src.api.server import app

        with TestClient(app) as client:
            resp = client.get("/analysis/detailed")

        assert resp.status_code == 200
        data = resp.json()
        assert data["data"] == []


class TestAnalysisMetricsEndpoint:
    """Tests for GET /analysis/metrics."""

    def test_metrics_with_data(self):
        reset_test_db()
        conn = get_conn()
        try:
            seed_anomaly_data(conn)
            from backend.src.api.server import app

            with TestClient(app) as client:
                resp = client.get("/analysis/metrics?hours=24")
                assert resp.status_code == 200
                data = resp.json()
                assert "time_series" in data
                assert "summary" in data
                assert "parameters" in data
                # Time series should contain data since we seeded anomalies
                assert len(data["time_series"]) > 0
        finally:
            release_conn(conn)

    def test_metrics_with_filters(self):
        """Filter by anomaly_type, severity, and is_active."""
        reset_test_db()
        conn = get_conn()
        try:
            seed_anomaly_data(conn)
            from backend.src.api.server import app

            with TestClient(app) as client:
                resp = client.get(
                    "/analysis/metrics",
                    params={
                        "hours": 24,
                        "anomaly_type": "A1",
                        "severity": "CRITICAL",
                        "bucket_minutes": 60,
                    },
                )
            assert resp.status_code == 200
            data = resp.json()
            assert data["parameters"]["anomaly_type"] == "A1"
            assert data["parameters"]["severity"] == "CRITICAL"
        finally:
            release_conn(conn)

    def test_metrics_no_data_returns_empty(self):
        reset_test_db()
        from backend.src.api.server import app

        with TestClient(app) as client:
            resp = client.get("/analysis/metrics?hours=168&bucket_minutes=1440")

        assert resp.status_code == 200
        data = resp.json()
        assert data["time_series"] == []
        assert "summary" in data
