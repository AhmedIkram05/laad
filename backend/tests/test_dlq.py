"""Tests for Redis Stream-based Dead Letter Queue."""

from unittest.mock import MagicMock, patch
import time


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

    @patch("backend.kafka.dlq.get_redis_client")
    def test_process_dlq_batch_retries_message(self, mock_get_client):
        """Test that DLQ processes and retries a message."""
        from backend.kafka.dlq import process_dlq_batch

        mock_client = MagicMock()
        old_time = time.time() - 60
        mock_client.xread.return_value = [
            ("ingestion:dlq", [
                ("1234567890-0", {
                    "raw_message": '{"test": 1}',
                    "error": "Parse error",
                    "source": "KAFKA",
                    "retry_count": "0",
                    "status": "pending",
                    "created_at": str(old_time),
                })
            ])
        ]
        mock_client.xadd.return_value = "1234567891-0"
        mock_get_client.return_value = mock_client

        result = process_dlq_batch(batch_size=10)

        assert result == 1
        mock_client.xdel.assert_called_once()

    @patch("backend.kafka.dlq.get_redis_client")
    def test_process_dlq_batch_marks_exhausted(self, mock_get_client):
        """Test that DLQ marks message as exhausted after max retries."""
        from backend.kafka.dlq import process_dlq_batch, MAX_RETRIES

        mock_client = MagicMock()
        old_time = time.time() - 60
        mock_client.xread.return_value = [
            ("ingestion:dlq", [
                ("1234567890-0", {
                    "raw_message": '{"test": 1}',
                    "error": "Parse error",
                    "source": "KAFKA",
                    "retry_count": str(MAX_RETRIES),
                    "status": "pending",
                    "created_at": str(old_time),
                })
            ])
        ]
        mock_client.xadd.return_value = "1234567891-0"
        mock_get_client.return_value = mock_client

        result = process_dlq_batch(batch_size=10)

        assert result == 1
        call_args = mock_client.xadd.call_args
        entry = call_args[0][1]
        assert entry["status"] == "exhausted"

    @patch("backend.kafka.dlq.get_redis_client")
    def test_process_dlq_batch_skips_not_ready(self, mock_get_client):
        """Test that DLQ skips messages that haven't reached backoff time."""
        from backend.kafka.dlq import process_dlq_batch

        mock_client = MagicMock()
        now = time.time()
        mock_client.xread.return_value = [
            ("ingestion:dlq", [
                ("1234567890-0", {
                    "raw_message": '{"test": 1}',
                    "error": "Parse error",
                    "source": "KAFKA",
                    "retry_count": "0",
                    "status": "pending",
                    "created_at": str(now),
                })
            ])
        ]
        mock_get_client.return_value = mock_client

        result = process_dlq_batch(batch_size=10)

        assert result == 0
        mock_client.xdel.assert_not_called()

    @patch("backend.kafka.dlq.get_redis_client")
    def test_process_dlq_batch_returns_zero_when_redis_down(self, mock_get_client):
        """Test that process returns 0 when Redis is unavailable."""
        from backend.kafka.dlq import process_dlq_batch

        mock_get_client.return_value = None

        result = process_dlq_batch(batch_size=10)

        assert result == 0
