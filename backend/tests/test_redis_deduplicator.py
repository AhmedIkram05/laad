"""Unit tests for Redis-backed Kafka deduplicator."""
from __future__ import annotations
import pytest
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
    def test_redis_sismember_used_for_duplicate_check(self, mock_get_client):
        """Test that Redis SISMEMBER is used for duplicate checks."""
        from backend.kafka.deduplicator import Deduplicator

        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_client.sismember.return_value = True
        mock_get_client.return_value = mock_client

        dedup = Deduplicator()
        dedup._use_redis = None

        result = dedup.is_duplicate("msg-redis-1")

        assert result is True
        mock_client.sismember.assert_called_once_with("kafka:dedup:seen", "msg-redis-1")

    @patch("backend.kafka.deduplicator.get_redis_client")
    def test_redis_sadd_used_for_mark_seen(self, mock_get_client):
        """Test that Redis SADD is used for marking seen."""
        from backend.kafka.deduplicator import Deduplicator

        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_client.sismember.return_value = False
        mock_get_client.return_value = mock_client

        dedup = Deduplicator()
        dedup._use_redis = None

        dedup.mark_seen("msg-redis-2")

        mock_client.sadd.assert_called_once_with("kafka:dedup:seen", "msg-redis-2")
        mock_client.expire.assert_called_once()

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
        mock_client.sismember.side_effect = Exception("Redis error")
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
        mock_client.sadd.side_effect = Exception("Redis error")
        mock_get_client.return_value = mock_client

        dedup = Deduplicator()
        dedup._use_redis = None

        dedup.mark_seen("msg-mark-fallback")
        assert dedup.is_duplicate("msg-mark-fallback") is True

    @patch("backend.kafka.deduplicator.get_redis_client")
    def test_redis_ttl_is_set(self, mock_get_client):
        """Test that TTL is set on the Redis dedup set."""
        from backend.kafka.deduplicator import Deduplicator

        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_client.sismember.return_value = False
        mock_get_client.return_value = mock_client

        dedup = Deduplicator(ttl_seconds=7200)
        dedup._use_redis = None

        dedup.mark_seen("msg-ttl-test")

        mock_client.expire.assert_called_once_with("kafka:dedup:seen", 7200)
