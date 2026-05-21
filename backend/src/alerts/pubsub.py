"""Real-time anomaly alerting via Redis Pub/Sub.

Publishes anomaly detection events to a Redis channel for live streaming
to connected dashboard clients via Server-Sent Events (SSE).

Usage:
    from backend.src.alerts.pubsub import publish_anomaly

    publish_anomaly({
        "anomaly_type": "A1",
        "atm_id": "ATM-GB-0001",
        "severity": "CRITICAL",
        "title": "ATM offline due to network failure.",
    })
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

from backend.src.cache import get_redis_client

logger = logging.getLogger(__name__)

ANOMALY_CHANNEL = "anomaly:detected"
ATM_RANK_KEY = "stats:atm:rank"


def publish_anomaly(anomaly_data: Dict[str, Any]) -> bool:
    """Publish an anomaly event to Redis Pub/Sub channel.

    Also increments the ATM ranking sorted set for real-time leaderboards.

    Returns True if published successfully, False if Redis is unavailable.
    """
    client = get_redis_client()
    if client is None:
        return False

    try:
        message = json.dumps(anomaly_data)
        client.publish(ANOMALY_CHANNEL, message)

        atm_id = anomaly_data.get("atm_id")
        if atm_id:
            client.zincrby(ATM_RANK_KEY, 1, atm_id)

        logger.debug(f"Published anomaly to Redis Pub/Sub: {anomaly_data.get('anomaly_type')}")
        return True

    except Exception as e:
        logger.warning(f"Failed to publish anomaly to Redis Pub/Sub: {e}")
        return False


def get_top_anomalous_atms(limit: int = 10) -> list:
    """Get the top N most anomalous ATMs from the Redis sorted set.

    Returns list of dicts: [{"atm_id": "...", "count": N}, ...]
    Falls back to empty list when Redis is unavailable.
    """
    client = get_redis_client()
    if client is None:
        return []

    try:
        results = client.zrevrange(ATM_RANK_KEY, 0, limit - 1, withscores=True)
        return [{"atm_id": atm_id, "count": int(score)} for atm_id, score in results]
    except Exception as e:
        logger.warning(f"Failed to get top anomalous ATMs: {e}")
        return []
