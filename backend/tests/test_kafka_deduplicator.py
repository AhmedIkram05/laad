"""Unit tests for Kafka deduplicator."""
from __future__ import annotations
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