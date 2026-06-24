"""Integration tests for analytics router endpoints via TestClient.

Complements test_analytics_counters.py (which tests the helper functions with mocks)
by exercising the actual FastAPI endpoints through TestClient.
"""

from fastapi.testclient import TestClient


class TestAnalyticsEventsEndpoint:
    """Tests for GET /api/analytics/events."""

    def test_events_returns_time_series(self):
        from backend.src.api.server import app

        with TestClient(app) as client:
            resp = client.get("/api/analytics/events?hours=24")

        assert resp.status_code == 200
        data = resp.json()
        assert "time_series" in data
        assert isinstance(data["time_series"], list)
        assert "parameters" in data
        assert data["parameters"]["hours"] == 24

    def test_events_all_time(self):
        """hours=0 returns all-time data with correct parameters."""
        from backend.src.api.server import app

        with TestClient(app) as client:
            resp = client.get("/api/analytics/events?hours=0")

        assert resp.status_code == 200
        data = resp.json()
        assert "time_series" in data
        assert data["parameters"]["hours"] == 0

    def test_events_with_bucket_and_source(self):
        """Custom bucket size and source filter."""
        from backend.src.api.server import app

        with TestClient(app) as client:
            resp = client.get(
                "/api/analytics/events",
                params={"hours": 24, "bucket_minutes": 30, "sources": "ATM_APP,HARDWARE"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["parameters"]["bucket_minutes"] == 30
        assert "ATM_APP" in data["parameters"]["sources"]

    def test_events_invalid_hours_returns_422(self):
        """hours below 0 should be rejected by query validation."""
        from backend.src.api.server import app

        with TestClient(app) as client:
            resp = client.get("/api/analytics/events?hours=-1")

        assert resp.status_code == 422


class TestAnalyticsMetricsEndpoint:
    """Tests for GET /api/analytics/metrics and /api/analytics/metrics/list."""

    def test_metrics_list_returns_list(self):
        from backend.src.api.server import app

        with TestClient(app) as client:
            resp = client.get("/api/analytics/metrics/list")

        assert resp.status_code == 200
        data = resp.json()
        assert "metrics" in data
        assert isinstance(data["metrics"], list)

    def test_metrics_timeline_returns_ok(self):
        from backend.src.api.server import app

        with TestClient(app) as client:
            resp = client.get("/api/analytics/metrics?hours=24")

        assert resp.status_code == 200
        data = resp.json()
        assert "time_series" in data
        assert "parameters" in data
        assert data["parameters"]["hours"] == 24


class TestAnalyticsEntitiesEndpoint:
    """Tests for GET /api/analytics/entities."""

    def test_entities_returns_list(self):
        from backend.src.api.server import app

        with TestClient(app) as client:
            resp = client.get("/api/analytics/entities")

        assert resp.status_code == 200
        data = resp.json()
        assert "entities" in data
        assert isinstance(data["entities"], list)


class TestAnalyticsRealtimeEndpoint:
    """Tests for GET /api/analytics/stats/realtime."""

    def test_realtime_stats_returns_structure(self):
        from backend.src.api.server import app

        with TestClient(app) as client:
            resp = client.get("/api/analytics/stats/realtime?hours=24")

        assert resp.status_code == 200
        data = resp.json()
        assert "events_by_source" in data
        assert "anomaly_types" in data
        assert "unique_atms" in data

    def test_realtime_stats_all_time(self):
        """hours=0 should work and not require Redis."""
        from backend.src.api.server import app

        with TestClient(app) as client:
            resp = client.get("/api/analytics/stats/realtime?hours=0")

        assert resp.status_code == 200
        data = resp.json()
        assert "events_by_source" in data
        assert "anomaly_types" in data
        assert "unique_atms" in data
