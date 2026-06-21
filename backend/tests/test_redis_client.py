"""Tests for shared Redis client module."""

from unittest.mock import MagicMock, patch


class TestRedisClient:
    """Test cases for shared Redis client functions."""

    def setup_method(self):
        from backend.src.cache import redis_client
        redis_client._redis_client = None
        redis_client._redis_connection_pool = None

    def teardown_method(self):
        from backend.src.cache import redis_client
        redis_client._redis_client = None
        redis_client._redis_connection_pool = None

    @patch("backend.src.cache.redis_client.redis.ConnectionPool")
    @patch("backend.src.cache.redis_client.redis.Redis")
    def test_get_redis_client_connects(self, mock_redis_class, mock_pool_class):
        """Test that Redis client connects successfully."""
        from backend.src.cache.redis_client import get_redis_client

        mock_instance = MagicMock()
        mock_instance.ping.return_value = True
        mock_redis_class.return_value = mock_instance

        mock_pool = MagicMock()
        mock_pool_class.return_value = mock_pool

        client = get_redis_client()

        assert client is not None
        mock_instance.ping.assert_called_once()
        mock_pool_class.assert_called_once()

    @patch("backend.src.cache.redis_client.redis.Redis")
    def test_get_redis_client_returns_none_on_failure(self, mock_redis_class):
        """Test that Redis client returns None on connection failure."""
        from backend.src.cache.redis_client import get_redis_client

        mock_redis_class.side_effect = Exception("Connection refused")

        client = get_redis_client()

        assert client is None

    @patch("backend.src.cache.redis_client.redis.Redis")
    def test_get_redis_client_returns_none_on_ping_failure(self, mock_redis_class):
        """Test that Redis client returns None when ping fails."""
        from backend.src.cache.redis_client import get_redis_client

        mock_instance = MagicMock()
        mock_instance.ping.side_effect = Exception("PONG not received")
        mock_redis_class.return_value = mock_instance

        client = get_redis_client()

        assert client is None

    @patch("backend.src.cache.redis_client.redis.ConnectionPool")
    @patch("backend.src.cache.redis_client.redis.Redis")
    def test_get_redis_client_is_singleton(self, mock_redis_class, mock_pool_class):
        """Test that get_redis_client returns the same instance."""
        from backend.src.cache.redis_client import get_redis_client

        mock_instance = MagicMock()
        mock_instance.ping.return_value = True
        mock_redis_class.return_value = mock_instance

        client1 = get_redis_client()
        client2 = get_redis_client()

        assert client1 is client2
        mock_redis_class.assert_called_once()

    def test_reset_redis_client(self):
        """Test that reset_redis_client clears the singleton."""
        from backend.src.cache.redis_client import get_redis_client, reset_redis_client

        with patch("backend.src.cache.redis_client.redis.ConnectionPool") as mock_pool_class, \
             patch("backend.src.cache.redis_client.redis.Redis") as mock_redis_class:  # noqa: F841

            mock_instance = MagicMock()
            mock_instance.ping.return_value = True
            mock_redis_class.return_value = mock_instance

            client1 = get_redis_client()
            assert client1 is not None

            reset_redis_client()

            mock_instance.close.assert_called_once()

            mock_redis_class.reset_mock()
            mock_instance2 = MagicMock()
            mock_instance2.ping.return_value = True
            mock_redis_class.return_value = mock_instance2

            client2 = get_redis_client()
            assert client2 is not None
            assert client2 is not client1

    def test_load_redis_config_defaults(self):
        """Test that config loads with defaults when env vars not set."""
        from backend.src.cache.redis_client import _load_redis_config

        with patch.dict("os.environ", {}, clear=False):
            import os
            for key in ["REDIS_HOST", "REDIS_PORT", "REDIS_DB", "REDIS_PASSWORD", "REDIS_CACHE_TTL"]:
                os.environ.pop(key, None)

            config = _load_redis_config()

            assert config["host"] == "localhost"
            assert config["port"] == 6379
            assert config["db"] == 0
            assert config["password"] is None
            assert config["cache_ttl"] == 300

    def test_load_redis_config_from_env(self):
        """Test that config loads from environment variables."""
        from backend.src.cache.redis_client import _load_redis_config

        with patch.dict("os.environ", {
            "REDIS_HOST": "my-redis-host",
            "REDIS_PORT": "6380",
            "REDIS_DB": "3",
            "REDIS_PASSWORD": "secret",
            "REDIS_CACHE_TTL": "600",
        }):
            config = _load_redis_config()

            assert config["host"] == "my-redis-host"
            assert config["port"] == 6380
            assert config["db"] == 3
            assert config["password"] == "secret"
            assert config["cache_ttl"] == 600

    def test_load_redis_config_invalid_port(self):
        """Test that invalid port falls back to default."""
        from backend.src.cache.redis_client import _load_redis_config

        with patch.dict("os.environ", {"REDIS_PORT": "not-a-number"}):
            config = _load_redis_config()
            assert config["port"] == 6379
