"""Tests for Redis Stream-based Dead Letter Queue."""

from unittest.mock import MagicMock, patch


class TestDLQ:
    """Test cases for Redis Stream DLQ."""

    @patch("backend.kafka.dlq.get_redis_client")
    def test_push_to_dlq_succeeds(self, mock_get_client):
        """Test that message is pushed to DLQ stream."""
        from backend.kafka.dlq import push_to_dlq

        mock_client = MagicMock()
        mock_client.xadd.return_value = "1234567890-0"
        mock_get_client.return_value = mock_client

        result = push_to_dlq({"message_id": "test-1"}, "Parse error", "KAFKA")

        assert result is True
        mock_client.xadd.assert_called_once()
        call_args = mock_client.xadd.call_args
        assert call_args[0][0] == "ingestion:dlq"
        entry = call_args[0][1]
        assert entry["error"] == "Parse error"
        assert entry["source"] == "KAFKA"
        assert entry["retry_count"] == "0"
        assert entry["status"] == "pending"

    @patch("backend.kafka.dlq.get_redis_client")
    def test_push_to_dlq_returns_false_when_redis_down(self, mock_get_client):
        """Test that push returns False when Redis is unavailable."""
        from backend.kafka.dlq import push_to_dlq

        mock_get_client.return_value = None

        result = push_to_dlq({"message_id": "test-2"}, "Error")

        assert result is False

    @patch("backend.kafka.dlq.get_redis_client")
    def test_push_to_dlq_handles_error(self, mock_get_client):
        """Test that push handles Redis errors gracefully."""
        from backend.kafka.dlq import push_to_dlq

        mock_client = MagicMock()
        mock_client.xadd.side_effect = Exception("Stream error")
        mock_get_client.return_value = mock_client

        result = push_to_dlq({"message_id": "test-3"}, "Error")

        assert result is False

    @patch("backend.kafka.dlq.get_redis_client")
    def test_get_dlq_length(self, mock_get_client):
        """Test that DLQ length is retrieved correctly."""
        from backend.kafka.dlq import get_dlq_length

        mock_client = MagicMock()
        mock_client.xlen.return_value = 42
        mock_get_client.return_value = mock_client

        result = get_dlq_length()

        assert result == 42
        mock_client.xlen.assert_called_once_with("ingestion:dlq")

    @patch("backend.kafka.dlq.get_redis_client")
    def test_get_dlq_length_zero_when_redis_down(self, mock_get_client):
        """Test that DLQ length returns 0 when Redis is unavailable."""
        from backend.kafka.dlq import get_dlq_length

        mock_get_client.return_value = None

        result = get_dlq_length()

        assert result == 0
