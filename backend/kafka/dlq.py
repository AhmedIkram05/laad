"""Dead Letter Queue (DLQ) for failed ingestion messages via Redis Streams.

Stores failed messages in a Redis Stream so they can be inspected later.
There is no in-process retry worker; messages stay in the stream.

Usage:
    from backend.kafka.dlq import push_to_dlq

    push_to_dlq({
        "raw_message": "...",
        "error": "Failed to parse",
        "source": "KAFKA",
    })
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from backend.src.cache import get_redis_client

logger = logging.getLogger(__name__)

DLQ_STREAM = "ingestion:dlq"


def push_to_dlq(raw_message: Any, error: str, source: str = "UNKNOWN") -> bool:
    """Push a failed message to the Redis Stream DLQ.

    Stores the raw message, error, source, retry count (0), and timestamp.
    Returns True if pushed successfully, False if Redis is unavailable.
    """
    client = get_redis_client()
    if client is None:
        return False

    try:
        entry = {
            "raw_message": json.dumps(raw_message)
            if not isinstance(raw_message, str)
            else raw_message,
            "error": error,
            "source": source,
            "retry_count": "0",
            "status": "pending",
            "created_at": str(time.time()),
        }
        client.xadd(DLQ_STREAM, entry)
        logger.debug(f"Pushed message to DLQ: source={source}, error={error}")
        return True

    except Exception as e:
        logger.warning(f"Failed to push to DLQ: {e}")
        return False


def get_dlq_length() -> int:
    """Get the number of pending messages in the DLQ."""
    client = get_redis_client()
    if client is None:
        return 0

    try:
        return client.xlen(DLQ_STREAM)
    except Exception as e:
        logger.warning(f"Failed to get DLQ length: {e}")
        return 0
