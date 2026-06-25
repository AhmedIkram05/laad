"""Tests for anomaly query caching via Redis."""

from unittest.mock import MagicMock, patch


class TestAnomalyQueryCache:
    """Test cases for Redis-based anomaly query caching."""

    def test_cache_key_is_deterministic(self):
        """Test that same params produce same cache key."""
        from backend.src.anomalies.anomalies_router import _get_cache_key

        params1 = {"atm_id": "ATM-GB-0001", "severity": "CRITICAL"}
        params2 = {"severity": "CRITICAL", "atm_id": "ATM-GB-0001"}

        key1 = _get_cache_key(params1)
        key2 = _get_cache_key(params2)

        assert key1 == key2
        assert key1.startswith("anomaly:list:")

    def test_cache_key_differs_for_different_params(self):
        """Test that different params produce different cache keys."""
        from backend.src.anomalies.anomalies_router import _get_cache_key

        key1 = _get_cache_key({"atm_id": "ATM-GB-0001"})
        key2 = _get_cache_key({"atm_id": "ATM-GB-0002"})

        assert key1 != key2

    @patch("backend.src.anomalies.anomalies_router.get_redis_client")
    def test_get_cached_result_returns_cached_data(self, mock_get_client):
        """Test that cached result is returned."""
        from backend.src.anomalies.anomalies_router import _get_cached_result
        import json

        mock_client = MagicMock()
        cached_data = {"total": 10, "data": []}
        mock_client.get.return_value = json.dumps(cached_data)
        mock_get_client.return_value = mock_client

        result = _get_cached_result({"atm_id": "ATM-GB-0001"})

        assert result == cached_data

    @patch("backend.src.anomalies.anomalies_router.get_redis_client")
    def test_get_cached_result_returns_none_on_miss(self, mock_get_client):
        """Test that cache miss returns None."""
        from backend.src.anomalies.anomalies_router import _get_cached_result

        mock_client = MagicMock()
        mock_client.get.return_value = None
        mock_get_client.return_value = mock_client

        result = _get_cached_result({"atm_id": "ATM-GB-0001"})

        assert result is None

    @patch("backend.src.anomalies.anomalies_router.get_redis_client")
    def test_get_cached_result_returns_none_when_redis_down(self, mock_get_client):
        """Test that cache returns None when Redis is unavailable."""
        from backend.src.anomalies.anomalies_router import _get_cached_result

        mock_get_client.return_value = None

        result = _get_cached_result({"atm_id": "ATM-GB-0001"})

        assert result is None

    @patch("backend.src.anomalies.anomalies_router.get_redis_client")
    def test_cache_result_stores_with_ttl(self, mock_get_client):
        """Test that result is cached with TTL."""
        from backend.src.anomalies.anomalies_router import _cache_result, CACHE_TTL

        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        result = {"total": 5, "data": []}
        _cache_result({"severity": "HIGH"}, result)

        mock_client.set.assert_called_once()
        call_args = mock_client.set.call_args
        assert call_args[0][0].startswith("anomaly:list:")
        assert call_args[1]["ex"] == CACHE_TTL

    @patch("backend.src.anomalies.anomalies_router.get_redis_client")
    def test_cache_result_noop_when_redis_down(self, mock_get_client):
        """Test that caching is a no-op when Redis is unavailable."""
        from backend.src.anomalies.anomalies_router import _cache_result

        mock_get_client.return_value = None

        _cache_result({"atm_id": "ATM-GB-0001"}, {"total": 0, "data": []})

    @patch("backend.src.anomalies.anomalies_router.get_redis_client")
    def test_invalidate_cache_deletes_keys(self, mock_get_client):
        """Test that cache invalidation deletes matching keys."""
        from backend.src.anomalies.anomalies_router import _invalidate_anomaly_cache

        mock_client = MagicMock()
        mock_client.keys.return_value = ["anomaly:list:abc123", "anomaly:list:def456"]
        mock_get_client.return_value = mock_client

        _invalidate_anomaly_cache()

        mock_client.delete.assert_called_once_with(
            "anomaly:list:abc123", "anomaly:list:def456"
        )

    @patch("backend.src.anomalies.anomalies_router.get_redis_client")
    def test_invalidate_cache_noop_when_redis_down(self, mock_get_client):
        """Test that invalidation is a no-op when Redis is unavailable."""
        from backend.src.anomalies.anomalies_router import _invalidate_anomaly_cache

        mock_get_client.return_value = None

        _invalidate_anomaly_cache()
