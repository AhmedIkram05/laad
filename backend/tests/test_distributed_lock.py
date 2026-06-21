"""Tests for distributed locking in Kafka consumer anomaly detection."""

from unittest.mock import MagicMock, patch


class TestDistributedLock:
    """Test cases for Redis-based distributed locking."""

    @patch("backend.kafka.consumer.get_redis_client")
    def test_lock_acquired_successfully(self, mock_get_client):
        """Test that lock is acquired when Redis returns True."""
        from backend.kafka.consumer import _acquire_detection_lock

        mock_client = MagicMock()
        mock_client.set.return_value = True
        mock_get_client.return_value = mock_client

        result = _acquire_detection_lock()

        assert result is True
        mock_client.set.assert_called_once_with(
            "lock:anomaly_detection", "1", nx=True, ex=25
        )

    @patch("backend.kafka.consumer.get_redis_client")
    def test_lock_not_acquired_when_held(self, mock_get_client):
        """Test that lock returns False when another consumer holds it."""
        from backend.kafka.consumer import _acquire_detection_lock

        mock_client = MagicMock()
        mock_client.set.return_value = False
        mock_get_client.return_value = mock_client

        result = _acquire_detection_lock()

        assert result is False

    @patch("backend.kafka.consumer.get_redis_client")
    def test_lock_proceeds_when_redis_unavailable(self, mock_get_client):
        """Test that detection proceeds when Redis is unavailable."""
        from backend.kafka.consumer import _acquire_detection_lock

        mock_get_client.return_value = None

        result = _acquire_detection_lock()

        assert result is True

    @patch("backend.kafka.consumer.get_redis_client")
    def test_lock_proceeds_on_redis_error(self, mock_get_client):
        """Test that detection proceeds when Redis throws an error."""
        from backend.kafka.consumer import _acquire_detection_lock

        mock_client = MagicMock()
        mock_client.set.side_effect = Exception("Redis error")
        mock_get_client.return_value = mock_client

        result = _acquire_detection_lock()

        assert result is True

    @patch("backend.kafka.consumer.get_redis_client")
    def test_release_lock_deletes_key(self, mock_get_client):
        """Test that releasing the lock deletes the Redis key."""
        from backend.kafka.consumer import _release_detection_lock

        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        _release_detection_lock()

        mock_client.delete.assert_called_once_with("lock:anomaly_detection")

    @patch("backend.kafka.consumer.get_redis_client")
    def test_release_lock_noop_when_redis_unavailable(self, mock_get_client):
        """Test that releasing is a no-op when Redis is unavailable."""
        from backend.kafka.consumer import _release_detection_lock

        mock_get_client.return_value = None

        _release_detection_lock()

    @patch("backend.kafka.consumer.get_redis_client")
    def test_lock_timeout_is_less_than_interval(self, mock_get_client):
        """Test that lock timeout is shorter than the trigger interval."""
        from backend.kafka.consumer import _acquire_detection_lock, LOCK_TIMEOUT_S, ANOMALY_INTERVAL_S

        mock_client = MagicMock()
        mock_client.set.return_value = True
        mock_get_client.return_value = mock_client

        _acquire_detection_lock()

        call_args = mock_client.set.call_args
        assert call_args[1]["ex"] == LOCK_TIMEOUT_S
        assert LOCK_TIMEOUT_S < ANOMALY_INTERVAL_S
