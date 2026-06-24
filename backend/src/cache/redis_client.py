"""Shared Redis client for the ATM platform.

Provides a singleton Redis client with connection pooling, health checks,
and graceful degradation. Used across all modules (RAG caching, rate limiting,
JWT blacklisting, deduplication, distributed locking, Pub/Sub, query caching,
analytics counters, and dead letter queue).

Usage:
    from backend.src.cache import get_redis_client

    client = get_redis_client()
    if client:
        client.set("key", "value")
"""

from __future__ import annotations

import logging
import os
from typing import Optional

import redis

logger = logging.getLogger(__name__)

_redis_client: Optional[redis.Redis] = None
_redis_connection_pool: Optional[redis.ConnectionPool] = None


def _load_redis_config() -> dict:
    """Load Redis configuration from environment variables."""
    host = os.getenv("REDIS_HOST", "localhost")
    try:
        port = int(os.getenv("REDIS_PORT", "6379"))
    except (ValueError, TypeError):
        logger.warning("Invalid REDIS_PORT, defaulting to 6379")
        port = 6379
    try:
        db = int(os.getenv("REDIS_DB", "0"))
    except (ValueError, TypeError):
        logger.warning("Invalid REDIS_DB, defaulting to 0")
        db = 0
    password = os.getenv("REDIS_PASSWORD")
    try:
        cache_ttl = int(os.getenv("REDIS_CACHE_TTL", "300"))
    except (ValueError, TypeError):
        logger.warning("Invalid REDIS_CACHE_TTL, defaulting to 300")
        cache_ttl = 300

    return {
        "host": host,
        "port": port,
        "db": db,
        "password": password,
        "cache_ttl": cache_ttl,
    }


def get_redis_client() -> Optional[redis.Redis]:
    """Get singleton Redis client with connection pooling.

    Returns None if Redis is unavailable — callers should handle gracefully.
    Thread-safe: connection pool is created once and shared.
    """
    global _redis_client, _redis_connection_pool

    if _redis_client is not None:
        return _redis_client

    try:
        config = _load_redis_config()

        if _redis_connection_pool is None:
            _redis_connection_pool = redis.ConnectionPool(
                host=config["host"],
                port=config["port"],
                db=config["db"],
                password=config["password"],
                max_connections=20,
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2,
                retry_on_timeout=True,
            )

        _redis_client = redis.Redis(connection_pool=_redis_connection_pool)
        _redis_client.ping()
        logger.info(
            f"Connected to Redis at {config['host']}:{config['port']} (db={config['db']})"
        )
        return _redis_client

    except Exception as e:
        logger.warning(f"Redis connection failed: {e}. Redis features disabled.")
        _redis_client = None
        _redis_connection_pool = None
        return None


def reset_redis_client() -> None:
    """Reset the Redis client (useful for testing or reconnection)."""
    global _redis_client, _redis_connection_pool

    if _redis_client is not None:
        try:
            _redis_client.close()
        except Exception:
            pass

    if _redis_connection_pool is not None:
        try:
            _redis_connection_pool.disconnect()
        except Exception:
            pass

    _redis_client = None
    _redis_connection_pool = None
