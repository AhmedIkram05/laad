"""Tests for distributed locking in Kafka consumer anomaly detection."""

from unittest.mock import MagicMock, patch


class TestDistributedLock:
    """Test cases for Redis-based distributed locking."""

    @patch("backend.kafka.consumer.get_redis_client")
    def test_lock_acquired_successfully(self, mock_get_client):
        """Test that the lock is acquired with a unique owner token."""
        from backend.kafka.consumer import _acquire_detection_lock

        mock_client = MagicMock()
        mock_client.set.return_value = True
        mock_get_client.return_value = mock_client

        should_run, token = _acquire_detection_lock()

        assert should_run is True
        assert token
        mock_client.set.assert_called_once()
        args, kwargs = mock_client.set.call_args
        assert args[0] == "lock:anomaly_detection"
        assert args[1] == token
        assert kwargs["nx"] is True
        assert "ex" in kwargs

    @patch("backend.kafka.consumer.get_redis_client")
    def test_lock_not_acquired_when_held(self, mock_get_client):
        """Test that no token is returned when another consumer holds the lock."""
        from backend.kafka.consumer import _acquire_detection_lock

        mock_client = MagicMock()
        mock_client.set.return_value = False
        mock_get_client.return_value = mock_client

        should_run, token = _acquire_detection_lock()

        assert should_run is False
        assert token is None

    @patch("backend.kafka.consumer.get_redis_client")
    def test_lock_proceeds_when_redis_unavailable(self, mock_get_client):
        """Test that detection proceeds when Redis is unavailable."""
        from backend.kafka.consumer import _acquire_detection_lock

        mock_get_client.return_value = None

        should_run, token = _acquire_detection_lock()

        assert should_run is True
        assert token is None

    @patch("backend.kafka.consumer.get_redis_client")
    def test_lock_proceeds_on_redis_error(self, mock_get_client):
        """Test that detection proceeds when Redis throws an error."""
        from backend.kafka.consumer import _acquire_detection_lock

        mock_client = MagicMock()
        mock_client.set.side_effect = Exception("Redis error")
        mock_get_client.return_value = mock_client

        should_run, token = _acquire_detection_lock()

        assert should_run is True
        assert token is None

    @patch("backend.kafka.consumer.get_redis_client")
    def test_release_lock_only_when_owner(self, mock_get_client):
        """Test that release is a token-checked compare-and-delete, not a bare delete."""
        from backend.kafka.consumer import _release_detection_lock

        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        _release_detection_lock("owner-token")

        mock_client.eval.assert_called_once()
        lua, numkeys, key, token = mock_client.eval.call_args.args
        assert token == "owner-token"
        assert key == "lock:anomaly_detection"
        # A stale owner must not delete a lock now held by someone else.
        mock_client.delete.assert_not_called()

    @patch("backend.kafka.consumer.get_redis_client")
    def test_release_lock_noop_when_redis_unavailable(self, mock_get_client):
        """Test that releasing is a no-op when Redis is unavailable or tokenless."""
        from backend.kafka.consumer import _release_detection_lock

        mock_get_client.return_value = None
        _release_detection_lock("owner-token")

        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        _release_detection_lock(None)

        mock_client.eval.assert_not_called()
        mock_client.delete.assert_not_called()

    @patch("backend.kafka.consumer.get_redis_client")
    def test_lock_timeout_is_floored_at_interval(self, mock_get_client):
        """Test that the lock TTL never goes non-positive and never expires mid-sweep."""
        from backend.kafka.consumer import (
            _acquire_detection_lock,
            LOCK_TIMEOUT_S,
            ANOMALY_INTERVAL_S,
        )

        mock_client = MagicMock()
        mock_client.set.return_value = True
        mock_get_client.return_value = mock_client

        _acquire_detection_lock()

        call_args = mock_client.set.call_args
        assert call_args[1]["ex"] == LOCK_TIMEOUT_S
        assert LOCK_TIMEOUT_S >= ANOMALY_INTERVAL_S
        assert LOCK_TIMEOUT_S > 0
