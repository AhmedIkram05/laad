"""Kafka message deduplicator with Redis-backed persistence.

Primary: per-message Redis keys (`SET <id> 1 EX ttl NX`) — the TTL is bounded
per key, so memory stays capped, and `check_and_mark()` does the whole
check+mark in a single round-trip.

Fallback: in-memory LRU OrderedDict — used when Redis is unavailable. When
Redis is down the availability is re-probed periodically (and immediately
after any Redis operation failure) instead of being cached for the life of
the process.

Usage:
    dedup = Deduplicator(max_size=10_000, ttl_seconds=3600)
    if dedup.check_and_mark(message_id):
        continue  # duplicate
"""

from __future__ import annotations

import logging
import time
from collections import OrderedDict
from typing import Optional


from backend.src.cache import get_redis_client

logger = logging.getLogger(__name__)

DEDUP_TTL_SECONDS = 3600
# Re-probe cadence while Redis is believed down, and cool-down after an
# in-flight operation fails (avoids hammering a flapping Redis per message).
_REDIS_PROBE_INTERVAL_S = 60.0
_REDIS_RETRY_PROBE_S = 5.0


class Deduplicator:
    """Hybrid deduplicator: Redis per-message keys (primary) + in-memory LRU (fallback)."""

    def __init__(self, max_size: int = 10_000, ttl_seconds: int = DEDUP_TTL_SECONDS):
        self._seen: OrderedDict[str, None] = OrderedDict()
        self._max_size = max_size
        self._ttl_seconds = ttl_seconds
        self._key_prefix = "kafka:dedup:id"
        self._use_redis: Optional[bool] = None
        self._probe_after: Optional[float] = None

    def _is_redis_available(self) -> bool:
        """Check if Redis is available for deduplication.

        An explicit False is sticky only when it was pinned (tests) or the
        re-probe window has not elapsed yet; Redis being down never pins the
        fallback for the life of the process.
        """
        if self._use_redis is True:
            return True
        if self._use_redis is False:
            if self._probe_after is None:
                return False
            if time.monotonic() < self._probe_after:
                return False

        client = get_redis_client()
        if client is not None:
            try:
                client.ping()
                self._use_redis = True
                self._probe_after = None
                return True
            except Exception:
                pass
        self._use_redis = False
        self._probe_after = time.monotonic() + _REDIS_PROBE_INTERVAL_S
        return False

    def _mark_redis_unavailable(self) -> None:
        self._use_redis = False
        self._probe_after = time.monotonic() + _REDIS_RETRY_PROBE_S

    def _check_and_mark_memory(self, message_id: str) -> bool:
        duplicate = message_id in self._seen
        if duplicate:
            self._seen.move_to_end(message_id)
        else:
            self._seen[message_id] = None
            while len(self._seen) > self._max_size:
                self._seen.popitem(last=False)
        return duplicate

    def check_and_mark(self, message_id: str) -> bool:
        """Mark message_id as seen and report whether it was already seen.

        Returns True when message_id was seen before (duplicate). One Redis
        round-trip on the happy path (SET NX EX returns None when the key
        already existed).
        """
        if not message_id:
            return False
        if self._is_redis_available():
            try:
                client = get_redis_client()
                if client is not None:
                    created = client.set(
                        f"{self._key_prefix}:{message_id}",
                        1,
                        nx=True,
                        ex=self._ttl_seconds,
                    )
                    return not created
            except Exception as e:
                logger.warning(
                    f"Redis dedup check failed, falling back to in-memory: {e}"
                )
                self._mark_redis_unavailable()
        return self._check_and_mark_memory(message_id)

    def is_duplicate(self, message_id: str) -> bool:
        """Check if a message_id has been seen before (without marking it)."""
        if not message_id:
            return False
        if self._is_redis_available():
            try:
                client = get_redis_client()
                if client is not None:
                    return bool(client.exists(f"{self._key_prefix}:{message_id}"))
            except Exception as e:
                logger.warning(
                    f"Redis dedup check failed, falling back to in-memory: {e}"
                )
                self._mark_redis_unavailable()

        return message_id in self._seen

    def mark_seen(self, message_id: str) -> None:
        """Mark a message_id as seen (idempotent)."""
        if self._is_redis_available():
            try:
                client = get_redis_client()
                if client is not None:
                    client.set(
                        f"{self._key_prefix}:{message_id}",
                        1,
                        ex=self._ttl_seconds,
                    )
            except Exception as e:
                logger.warning(
                    f"Redis dedup mark_seen failed, falling back to in-memory: {e}"
                )
                self._mark_redis_unavailable()

        if message_id in self._seen:
            self._seen.move_to_end(message_id)
        else:
            self._seen[message_id] = None
            if len(self._seen) > self._max_size:
                self._seen.popitem(last=False)
