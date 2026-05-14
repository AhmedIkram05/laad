"""In-memory LRU deduplicator for Kafka consumer.

Tracks the last N message_ids seen to prevent duplicate inserts
when Kafka redelivers messages (at-least-once guarantee).

The LRU set is per-process — if the consumer restarts it resets,
which means duplicate inserts are possible immediately after restart.
This is acceptable for at-least-once delivery.

Usage:
    dedup = Deduplicator(max_size=10_000)
    if dedup.is_duplicate(message_id):
        continue
    dedup.mark_seen(message_id)
"""
from __future__ import annotations

from collections import OrderedDict


class Deduplicator:
    def __init__(self, max_size: int = 10_000):
        self._seen: OrderedDict[str, None] = OrderedDict()
        self._max_size = max_size

    def is_duplicate(self, message_id: str) -> bool:
        return message_id in self._seen

    def mark_seen(self, message_id: str) -> None:
        if message_id in self._seen:
            self._seen.move_to_end(message_id)
        else:
            self._seen[message_id] = None
            if len(self._seen) > self._max_size:
                self._seen.popitem(last=False)