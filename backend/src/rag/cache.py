"""Redis-based response caching for RAG queries."""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Optional

from backend.src.cache import get_redis_client
from backend.src.rag.config import config

logger = logging.getLogger(__name__)


def get_query_hash(query: str) -> str:
    """Generate a short hash for a query string."""
    return hashlib.sha256(query.lower().strip().encode()).hexdigest()[:16]


def get_cached_response(query: str) -> Optional[dict]:
    """Get cached response for a query. Returns None on cache miss or error."""
    try:
        client = get_redis_client()
        if client is None:
            return None
        key = f"rag:response:{get_query_hash(query)}"
        cached = client.get(key)
        if cached:
            logger.info(f"Cache hit for query hash {get_query_hash(query)}")
            return json.loads(cached)
        return None
    except Exception as e:
        logger.warning(f"Redis cache get failed: {e}")
        return None


def set_cached_response(query: str, response: dict) -> None:
    """Cache a response for a query with TTL."""
    try:
        client = get_redis_client()
        if client is None:
            return
        key = f"rag:response:{get_query_hash(query)}"
        client.setex(key, config.cache_ttl, json.dumps(response))
        logger.info(
            f"Cached response for query hash {get_query_hash(query)} (TTL={config.cache_ttl}s)"
        )
    except Exception as e:
        logger.warning(f"Redis cache set failed: {e}")
