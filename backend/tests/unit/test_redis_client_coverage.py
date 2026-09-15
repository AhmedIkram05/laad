"""Coverage tests for backend.src.cache.redis_client."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


class TestLoadRedisConfigInvalidDb:
    """Test _load_redis_config with invalid REDIS_DB values."""

    def test_invalid_db_non_numeric_returns_default(self):
        """Non-numeric REDIS_DB falls back to 0."""
        from backend.src.cache.redis_client import _load_redis_config

        with patch.dict("os.environ", {"REDIS_DB": "not-a-number"}):
            config = _load_redis_config()
            assert config["db"] == 0

    def test_invalid_db_float_string_returns_default(self):
        """Float string REDIS_DB falls back to 0."""
        from backend.src.cache.redis_client import _load_redis_config

        with patch.dict("os.environ", {"REDIS_DB": "1.5"}):
            config = _load_redis_config()
            assert config["db"] == 0

    def test_invalid_db_empty_string_returns_default(self):
        """Empty string REDIS_DB falls back to 0."""
        from backend.src.cache.redis_client import _load_redis_config

        with patch.dict("os.environ", {"REDIS_DB": ""}):
            config = _load_redis_config()
            assert config["db"] == 0


class TestLoadRedisConfigInvalidCacheTtl:
    """Test _load_redis_config with invalid REDIS_CACHE_TTL values."""

    def test_invalid_ttl_non_numeric_returns_default(self):
        """Non-numeric REDIS_CACHE_TTL falls back to 300."""
        from backend.src.cache.redis_client import _load_redis_config

        with patch.dict("os.environ", {"REDIS_CACHE_TTL": "abc"}):
            config = _load_redis_config()
            assert config["cache_ttl"] == 300

    def test_invalid_ttl_float_string_returns_default(self):
        """Float string REDIS_CACHE_TTL falls back to 300."""
        from backend.src.cache.redis_client import _load_redis_config

        with patch.dict("os.environ", {"REDIS_CACHE_TTL": "60.5"}):
            config = _load_redis_config()
            assert config["cache_ttl"] == 300

    def test_invalid_ttl_empty_string_returns_default(self):
        """Empty string REDIS_CACHE_TTL falls back to 300."""
        from backend.src.cache.redis_client import _load_redis_config

        with patch.dict("os.environ", {"REDIS_CACHE_TTL": ""}):
            config = _load_redis_config()
            assert config["cache_ttl"] == 300


class TestLoadRedisConfigPartialOverrides:
    """Test _load_redis_config with partial environment overrides."""

    def test_only_host_set(self):
        """Only REDIS_HOST set; other values use defaults."""
        from backend.src.cache.redis_client import _load_redis_config

        with patch.dict("os.environ", {"REDIS_HOST": "custom-host"}):
            config = _load_redis_config()
            assert config["host"] == "custom-host"
            assert config["port"] == 6379
            assert config["db"] == 0
            assert config["cache_ttl"] == 300

    def test_only_port_set(self):
        """Only REDIS_PORT set; other values use defaults."""

        from backend.src.cache.redis_client import _load_redis_config

        with patch.dict("os.environ", {"REDIS_PORT": "7000"}, clear=True):
            config = _load_redis_config()
            assert config["host"] == "localhost"
            assert config["port"] == 7000
            assert config["db"] == 0


class TestLoadRedisConfigPassword:
    """Test _load_redis_config password handling."""

    def test_password_none_when_not_set(self):
        """REDIS_PASSWORD not set returns None."""
        import os

        from backend.src.cache.redis_client import _load_redis_config

        with patch.dict("os.environ", {}, clear=False):
            os.environ.pop("REDIS_PASSWORD", None)
            config = _load_redis_config()
            assert config["password"] is None

    def test_password_set_from_env(self):
        """REDIS_PASSWORD set returns the value."""
        from backend.src.cache.redis_client import _load_redis_config

        with patch.dict("os.environ", {"REDIS_PASSWORD": "s3cret"}):
            config = _load_redis_config()
            assert config["password"] == "s3cret"

    def test_empty_password_string(self):
        """Empty REDIS_PASSWORD returns empty string."""
        from backend.src.cache.redis_client import _load_redis_config

        with patch.dict("os.environ", {"REDIS_PASSWORD": ""}):
            config = _load_redis_config()
            assert config["password"] == ""


class TestLoadRedisConfigInvalidPort:
    """Test _load_redis_config with various invalid port values."""

    def test_invalid_port_empty_string_returns_default(self):
        """Empty string REDIS_PORT falls back to 6379."""
        from backend.src.cache.redis_client import _load_redis_config

        with patch.dict("os.environ", {"REDIS_PORT": ""}):
            config = _load_redis_config()
            assert config["port"] == 6379

    def test_invalid_port_float_string_returns_default(self):
        """Float string REDIS_PORT falls back to 6379."""
        from backend.src.cache.redis_client import _load_redis_config

        with patch.dict("os.environ", {"REDIS_PORT": "6379.5"}):
            config = _load_redis_config()
            assert config["port"] == 6379


class TestGetRedisClientConnectionPoolParams:
    """Test that ConnectionPool is created with correct parameters."""

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
    def test_connection_pool_decode_responses_true(
        self, mock_redis_class, mock_pool_class
    ):
        """ConnectionPool is created with decode_responses=True."""
        from backend.src.cache.redis_client import get_redis_client

        mock_instance = MagicMock()
        mock_instance.ping.return_value = True
        mock_redis_class.return_value = mock_instance

        mock_pool = MagicMock()
        mock_pool_class.return_value = mock_pool

        get_redis_client()

        call_kwargs = mock_pool_class.call_args[1]
        assert call_kwargs["decode_responses"] is True

    @patch("backend.src.cache.redis_client.redis.ConnectionPool")
    @patch("backend.src.cache.redis_client.redis.Redis")
    def test_connection_pool_max_connections(self, mock_redis_class, mock_pool_class):
        """ConnectionPool is created with max_connections=20."""
        from backend.src.cache.redis_client import get_redis_client

        mock_instance = MagicMock()
        mock_instance.ping.return_value = True
        mock_redis_class.return_value = mock_instance

        mock_pool = MagicMock()
        mock_pool_class.return_value = mock_pool

        get_redis_client()

        call_kwargs = mock_pool_class.call_args[1]
        assert call_kwargs["max_connections"] == 20

    @patch("backend.src.cache.redis_client.redis.ConnectionPool")
    @patch("backend.src.cache.redis_client.redis.Redis")
    def test_connection_pool_retry_on_timeout(self, mock_redis_class, mock_pool_class):
        """ConnectionPool is created with retry_on_timeout=True."""
        from backend.src.cache.redis_client import get_redis_client

        mock_instance = MagicMock()
        mock_instance.ping.return_value = True
        mock_redis_class.return_value = mock_instance

        mock_pool = MagicMock()
        mock_pool_class.return_value = mock_pool

        get_redis_client()

        call_kwargs = mock_pool_class.call_args[1]
        assert call_kwargs["retry_on_timeout"] is True

    @patch("backend.src.cache.redis_client.redis.ConnectionPool")
    @patch("backend.src.cache.redis_client.redis.Redis")
    def test_connection_pool_reused_on_second_call(
        self, mock_redis_class, mock_pool_class
    ):
        """ConnectionPool is not recreated on second get_redis_client call."""
        from backend.src.cache.redis_client import get_redis_client

        mock_instance = MagicMock()
        mock_instance.ping.return_value = True
        mock_redis_class.return_value = mock_instance

        mock_pool = MagicMock()
        mock_pool_class.return_value = mock_pool

        get_redis_client()
        get_redis_client()

        mock_pool_class.assert_called_once()

    @patch("backend.src.cache.redis_client.redis.ConnectionPool")
    @patch("backend.src.cache.redis_client.redis.Redis")
    def test_connection_pool_socket_timeout(self, mock_redis_class, mock_pool_class):
        """ConnectionPool is created with socket_timeout=2."""
        from backend.src.cache.redis_client import get_redis_client

        mock_instance = MagicMock()
        mock_instance.ping.return_value = True
        mock_redis_class.return_value = mock_instance

        mock_pool = MagicMock()
        mock_pool_class.return_value = mock_pool

        get_redis_client()

        call_kwargs = mock_pool_class.call_args[1]
        assert call_kwargs["socket_timeout"] == 2
        assert call_kwargs["socket_connect_timeout"] == 2


class TestGetRedisClientConnectionError:
    """Test get_redis_client when ping raises ConnectionError."""

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
    def test_connection_error_returns_none(self, mock_redis_class, mock_pool_class):
        """ConnectionError from ping() returns None."""
        from backend.src.cache.redis_client import get_redis_client

        mock_instance = MagicMock()
        mock_instance.ping.side_effect = ConnectionError("Connection refused")
        mock_redis_class.return_value = mock_instance

        mock_pool = MagicMock()
        mock_pool_class.return_value = mock_pool

        client = get_redis_client()

        assert client is None


class TestResetRedisClientNoop:
    """Test reset_redis_client when client is None (no-op path)."""

    def test_reset_when_client_is_none_does_not_raise(self):
        """Calling reset when _redis_client is None does not raise."""
        from backend.src.cache import redis_client
        from backend.src.cache.redis_client import reset_redis_client

        redis_client._redis_client = None
        redis_client._redis_connection_pool = None

        reset_redis_client()

        assert redis_client._redis_client is None
        assert redis_client._redis_connection_pool is None

    def test_reset_when_only_pool_is_none(self):
        """Calling reset when pool is None but client exists."""
        from backend.src.cache import redis_client
        from backend.src.cache.redis_client import reset_redis_client

        mock_client = MagicMock()
        redis_client._redis_client = mock_client
        redis_client._redis_connection_pool = None

        reset_redis_client()

        mock_client.close.assert_called_once()
        assert redis_client._redis_client is None
        assert redis_client._redis_connection_pool is None

    def test_reset_when_close_raises(self):
        """Calling reset when client.close() raises does not propagate."""
        from backend.src.cache import redis_client
        from backend.src.cache.redis_client import reset_redis_client

        mock_client = MagicMock()
        mock_client.close.side_effect = Exception("already closed")
        redis_client._redis_client = mock_client
        redis_client._redis_connection_pool = None

        reset_redis_client()

        assert redis_client._redis_client is None
        assert redis_client._redis_connection_pool is None

    def test_reset_when_pool_disconnect_raises(self):
        """Calling reset when pool.disconnect() raises does not propagate."""
        from backend.src.cache import redis_client
        from backend.src.cache.redis_client import reset_redis_client

        mock_client = MagicMock()
        mock_pool = MagicMock()
        mock_pool.disconnect.side_effect = Exception("already disconnected")
        redis_client._redis_client = mock_client
        redis_client._redis_connection_pool = mock_pool

        reset_redis_client()

        mock_client.close.assert_called_once()
        mock_pool.disconnect.assert_called_once()
        assert redis_client._redis_client is None
        assert redis_client._redis_connection_pool is None


class TestGetRedisClientPoolAlreadyInitialized:
    """Test get_redis_client when connection pool already exists."""

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
    def test_reuses_existing_pool(self, mock_redis_class, mock_pool_class):
        """When pool already exists, a new pool is not created."""
        from backend.src.cache import redis_client
        from backend.src.cache.redis_client import get_redis_client

        existing_pool = MagicMock()
        redis_client._redis_connection_pool = existing_pool

        mock_instance = MagicMock()
        mock_instance.ping.return_value = True
        mock_redis_class.return_value = mock_instance

        client = get_redis_client()

        assert client is not None
        mock_pool_class.assert_not_called()

    @patch("backend.src.cache.redis_client.redis.ConnectionPool")
    @patch("backend.src.cache.redis_client.redis.Redis")
    def test_uses_existing_pool_for_new_client(self, mock_redis_class, mock_pool_class):
        """When pool exists, new client uses it instead of creating new."""
        from backend.src.cache import redis_client
        from backend.src.cache.redis_client import get_redis_client

        existing_pool = MagicMock()
        redis_client._redis_connection_pool = existing_pool

        mock_instance = MagicMock()
        mock_instance.ping.return_value = True
        mock_redis_class.return_value = mock_instance

        get_redis_client()

        mock_redis_class.assert_called_once_with(connection_pool=existing_pool)
