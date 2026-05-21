"""Tests for Redis analytics counters and HyperLogLog."""

import pytest
from unittest.mock import MagicMock, patch


class TestAnalyticsCounters:
    """Test cases for Redis-based analytics counters."""

    @patch("backend.src.analytics.analytics_router.get_redis_client")
    def test_increment_event_counter(self, mock_get_client):
        """Test that event counter is incremented."""
        from backend.src.analytics.analytics_router import increment_event_counter

        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        increment_event_counter("ATM_APP", "2026-05-20-14")

        mock_client.incr.assert_called_once()
        mock_client.expire.assert_called_once()

    @patch("backend.src.analytics.analytics_router.get_redis_client")
    def test_increment_event_counter_noop_when_redis_down(self, mock_get_client):
        """Test that counter increment is a no-op when Redis is unavailable."""
        from backend.src.analytics.analytics_router import increment_event_counter

        mock_get_client.return_value = None

        increment_event_counter("ATM_APP", "2026-05-20-14")

    @patch("backend.src.analytics.analytics_router.get_redis_client")
    def test_increment_anomaly_counter(self, mock_get_client):
        """Test that anomaly counter is incremented via sorted set."""
        from backend.src.analytics.analytics_router import increment_anomaly_counter

        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        increment_anomaly_counter("A1", "2026-05-20-14")

        mock_client.zincrby.assert_called_once()
        mock_client.expire.assert_called_once()

    @patch("backend.src.analytics.analytics_router.get_redis_client")
    def test_track_unique_atm(self, mock_get_client):
        """Test that ATM ID is added to HyperLogLog."""
        from backend.src.analytics.analytics_router import track_unique_atm

        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        track_unique_atm("ATM-GB-0001")

        mock_client.pfadd.assert_called_once_with("stats:unique:atms", "ATM-GB-0001")
        mock_client.expire.assert_called_once()

    @patch("backend.src.analytics.analytics_router.get_redis_client")
    def test_track_unique_atm_noop_when_redis_down(self, mock_get_client):
        """Test that tracking is a no-op when Redis is unavailable."""
        from backend.src.analytics.analytics_router import track_unique_atm

        mock_get_client.return_value = None

        track_unique_atm("ATM-GB-0001")

    @patch("backend.src.analytics.analytics_router.get_redis_client")
    def test_get_unique_atm_count(self, mock_get_client):
        """Test that unique ATM count is retrieved from HyperLogLog."""
        from backend.src.analytics.analytics_router import get_unique_atm_count

        mock_client = MagicMock()
        mock_client.pfcount.return_value = 10
        mock_get_client.return_value = mock_client

        result = get_unique_atm_count()

        assert result == 10
        mock_client.pfcount.assert_called_once_with("stats:unique:atms")

    @patch("backend.src.analytics.analytics_router.get_redis_client")
    def test_get_unique_atm_count_zero_when_redis_down(self, mock_get_client):
        """Test that count returns 0 when Redis is unavailable."""
        from backend.src.analytics.analytics_router import get_unique_atm_count

        mock_get_client.return_value = None

        result = get_unique_atm_count()

        assert result == 0

    @patch("backend.src.analytics.analytics_router.get_redis_client")
    def test_realtime_stats_endpoint(self, mock_get_client):
        """Test that the realtime stats endpoint returns the expected structure."""
        from backend.src.analytics.analytics_router import get_realtime_stats

        mock_client = MagicMock()
        mock_client.keys.side_effect = lambda pattern: {
            "stats:events:*": ["stats:events:ATM_APP:2026-05-20-14"],
            "stats:anomaly:type:*": ["stats:anomaly:type:2026-05-20-14"],
        }.get(pattern, [])
        mock_client.get.return_value = "42"
        mock_client.zrange.return_value = [("A1", 5.0)]
        mock_client.pfcount.return_value = 10
        mock_get_client.return_value = mock_client

        result = get_realtime_stats(hours=24)

        assert "events_by_source" in result
        assert "anomaly_types" in result
        assert "unique_atms" in result

    @patch("backend.src.analytics.analytics_router.get_redis_client")
    def test_realtime_stats_empty_when_redis_down(self, mock_get_client):
        """Test that realtime stats returns empty data when Redis is unavailable."""
        from backend.src.analytics.analytics_router import get_realtime_stats

        mock_get_client.return_value = None

        result = get_realtime_stats(hours=24)

        assert "events_by_source" in result
        assert "anomaly_types" in result
        assert "unique_atms" in result
