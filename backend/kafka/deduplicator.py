"""Kafka message deduplicator with Redis-backed persistence.

Primary: Redis Set with TTL — persists across consumer restarts,
eliminating duplicate inserts after restart.

Fallback: In-memory LRU OrderedDict — used when Redis is unavailable.

Usage:
    dedup = Deduplicator(max_size=10_000, ttl_seconds=3600)
    if dedup.is_duplicate(message_id):
        continue
    dedup.mark_seen(message_id)
"""
from __future__ import annotations

import logging
from collections import OrderedDict
from typing import Optional

import redis

from backend.src.cache import get_redis_client

logger = logging.getLogger(__name__)

DEDUP_TTL_SECONDS = 3600


class Deduplicator:
    """Hybrid deduplicator: Redis Set (primary) + in-memory LRU (fallback)."""

    def __init__(self, max_size: int = 10_000, ttl_seconds: int = DEDUP_TTL_SECONDS):
        self._seen: OrderedDict[str, None] = OrderedDict()
        self._max_size = max_size
        self._ttl_seconds = ttl_seconds
        self._redis_key = "kafka:dedup:seen"
        self._use_redis: Optional[bool] = None

    def _is_redis_available(self) -> bool:
        """Check if Redis is available for deduplication."""
        if self._use_redis is not None:
            return self._use_redis

        client = get_redis_client()
        if client is not None:
            try:
                client.ping()
                self._use_redis = True
                return True
            except Exception:
                self._use_redis = False
                return False
        self._use_redis = False
        return False

    def is_duplicate(self, message_id: str) -> bool:
        """Check if a message_id has been seen before."""
        if self._is_redis_available():
            try:
                client = get_redis_client()
                if client is not None:
                    return bool(client.sismember(self._redis_key, message_id))
            except Exception as e:
                logger.warning(f"Redis dedup check failed, falling back to in-memory: {e}")
                self._use_redis = False

        return message_id in self._seen

    def mark_seen(self, message_id: str) -> None:
        """Mark a message_id as seen."""
        if self._is_redis_available():
            try:
                client = get_redis_client()
                if client is not None:
                    client.sadd(self._redis_key, message_id)
                    client.expire(self._redis_key, self._ttl_seconds)
            except Exception as e:
                logger.warning(f"Redis dedup mark_seen failed, falling back to in-memory: {e}")
                self._use_redis = False

        if message_id in self._seen:
            self._seen.move_to_end(message_id)
        else:
            self._seen[message_id] = None
            if len(self._seen) > self._max_size:
                self._seen.popitem(last=False)
