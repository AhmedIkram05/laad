"""Unit tests for Redis-backed Kafka deduplicator."""

from __future__ import annotations
from unittest.mock import MagicMock, patch
from backend.kafka.deduplicator import Deduplicator


class TestDeduplicator:
    def test_new_message_not_duplicate(self):
        dedup = Deduplicator(max_size=10)
        dedup._use_redis = False
        assert dedup.is_duplicate("msg-1") is False

    def test_mark_seen_then_check_is_duplicate(self):
        dedup = Deduplicator(max_size=10)
        dedup._use_redis = False
        dedup.mark_seen("msg-1")
        assert dedup.is_duplicate("msg-1") is True

    def test_same_id_not_duplicate_twice(self):
        dedup = Deduplicator(max_size=10)
        dedup._use_redis = False
        dedup.mark_seen("msg-1")
        dedup.mark_seen("msg-1")
        assert dedup.is_duplicate("msg-1") is True

    def test_lru_eviction(self):
        dedup = Deduplicator(max_size=3)
        dedup._use_redis = False
        for i in range(5):
            dedup.mark_seen(f"msg-{i}")
        assert dedup.is_duplicate("msg-0") is False
        assert dedup.is_duplicate("msg-1") is False
        assert dedup.is_duplicate("msg-2") is True
        assert dedup.is_duplicate("msg-3") is True
        assert dedup.is_duplicate("msg-4") is True

    def test_move_to_end_on_revisit(self):
        dedup = Deduplicator(max_size=3)
        dedup._use_redis = False
        dedup.mark_seen("a")
        dedup.mark_seen("b")
        dedup.mark_seen("c")
        dedup.mark_seen("a")
        assert dedup.is_duplicate("b") is True
        assert dedup.is_duplicate("c") is True
        assert dedup.is_duplicate("a") is True

    def test_empty_id_not_duplicate(self):
        dedup = Deduplicator(max_size=10)
        dedup._use_redis = False
        assert dedup.is_duplicate("") is False

    def test_max_size_zero(self):
        dedup = Deduplicator(max_size=0)
        dedup._use_redis = False
        dedup.mark_seen("msg-1")
        assert dedup.is_duplicate("msg-1") is False


class TestDeduplicatorRedis:
    """Test Redis-backed deduplication behavior."""

    @patch("backend.kafka.deduplicator.get_redis_client")
    def test_redis_exists_used_for_duplicate_check(self, mock_get_client):
        """Test that Redis EXISTS on the per-message key is used for checks."""
        from backend.kafka.deduplicator import Deduplicator

        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_client.exists.return_value = True
        mock_get_client.return_value = mock_client

        dedup = Deduplicator()
        dedup._use_redis = None

        result = dedup.is_duplicate("msg-redis-1")

        assert result is True
        mock_client.exists.assert_called_once_with("kafka:dedup:id:msg-redis-1")

    @patch("backend.kafka.deduplicator.get_redis_client")
    def test_redis_set_used_for_mark_seen(self, mock_get_client):
        """Test that Redis SET with a bounded per-key TTL is used for mark_seen."""
        from backend.kafka.deduplicator import Deduplicator

        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_get_client.return_value = mock_client

        dedup = Deduplicator()
        dedup._use_redis = None

        dedup.mark_seen("msg-redis-2")

        mock_client.set.assert_called_once_with(
            "kafka:dedup:id:msg-redis-2", 1, ex=3600
        )
        # No shared sliding-EXPIRE set anymore.
        mock_client.sadd.assert_not_called()
        mock_client.expire.assert_not_called()

    @patch("backend.kafka.deduplicator.get_redis_client")
    def test_fallback_to_in_memory_when_redis_fails(self, mock_get_client):
        """Test fallback to in-memory when Redis is unavailable."""
        from backend.kafka.deduplicator import Deduplicator

        mock_get_client.return_value = None

        dedup = Deduplicator()
        dedup._use_redis = None

        dedup.mark_seen("msg-fallback-1")
        assert dedup.is_duplicate("msg-fallback-1") is True

    @patch("backend.kafka.deduplicator.get_redis_client")
    def test_redis_persists_across_instances(self, mock_get_client):
        """Test that Redis dedup persists across Deduplicator instances."""
        from backend.kafka.deduplicator import Deduplicator

        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_client.sismember.return_value = True
        mock_get_client.return_value = mock_client

        dedup1 = Deduplicator()
        dedup1._use_redis = None
        dedup1.mark_seen("msg-persist")

        dedup2 = Deduplicator()
        dedup2._use_redis = None

        assert dedup2.is_duplicate("msg-persist") is True

    @patch("backend.kafka.deduplicator.get_redis_client")
    def test_redis_failure_during_check_falls_back(self, mock_get_client):
        """Test that Redis failure during is_duplicate falls back to in-memory."""
        from backend.kafka.deduplicator import Deduplicator

        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_client.exists.side_effect = Exception("Redis error")
        mock_client.set.side_effect = Exception("Redis error")
        mock_get_client.return_value = mock_client

        dedup = Deduplicator()
        dedup._use_redis = None

        dedup.mark_seen("msg-error-fallback")
        result = dedup.is_duplicate("msg-error-fallback")

        assert result is True

    @patch("backend.kafka.deduplicator.get_redis_client")
    def test_redis_failure_during_mark_falls_back(self, mock_get_client):
        """Test that Redis failure during mark_seen falls back to in-memory."""
        from backend.kafka.deduplicator import Deduplicator

        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_client.set.side_effect = Exception("Redis error")
        mock_get_client.return_value = mock_client

        dedup = Deduplicator()
        dedup._use_redis = None

        dedup.mark_seen("msg-mark-fallback")
        assert dedup.is_duplicate("msg-mark-fallback") is True

    @patch("backend.kafka.deduplicator.get_redis_client")
    def test_redis_ttl_is_set(self, mock_get_client):
        """Test that the TTL is set on each per-message dedup key."""
        from backend.kafka.deduplicator import Deduplicator

        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_get_client.return_value = mock_client

        dedup = Deduplicator(ttl_seconds=7200)
        dedup._use_redis = None

        dedup.mark_seen("msg-ttl-test")

        mock_client.set.assert_called_once_with(
            "kafka:dedup:id:msg-ttl-test", 1, ex=7200
        )

    @patch("backend.kafka.deduplicator.get_redis_client")
    def test_mark_batch_uses_single_pipeline(self, mock_get_client):
        """mark_batch writes all keys through one pipelined round-trip."""
        from backend.kafka.deduplicator import Deduplicator

        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_pipe = MagicMock()
        mock_client.pipeline.return_value = mock_pipe
        mock_get_client.return_value = mock_client

        dedup = Deduplicator()
        dedup._use_redis = None

        dedup.mark_batch(["a", "b", ""])

        assert mock_client.pipeline.call_count == 1
        assert mock_pipe.set.call_count == 2
        mock_pipe.set.assert_any_call("kafka:dedup:id:a", 1, ex=3600)
        mock_pipe.set.assert_any_call("kafka:dedup:id:b", 1, ex=3600)
        mock_pipe.execute.assert_called_once_with()

    @patch("backend.kafka.deduplicator.get_redis_client")
    def test_mark_batch_redis_failure_falls_back_to_memory(self, mock_get_client):
        from backend.kafka.deduplicator import Deduplicator

        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_client.pipeline.side_effect = Exception("Redis error")
        mock_get_client.return_value = mock_client

        dedup = Deduplicator()
        dedup._use_redis = None

        dedup.mark_batch(["m-fb"])
        assert dedup.is_duplicate("m-fb") is True
