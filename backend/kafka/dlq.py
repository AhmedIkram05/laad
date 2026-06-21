"""Dead Letter Queue (DLQ) for failed ingestion messages via Redis Streams.

Stores failed messages in a Redis Stream with retry count, error details,
and exponential backoff. A background worker processes the DLQ and retries
failed messages up to a maximum count.

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
MAX_RETRIES = 3
BASE_BACKOFF_SECONDS = 5


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
            "raw_message": json.dumps(raw_message) if not isinstance(raw_message, str) else raw_message,
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


def process_dlq_batch(batch_size: int = 10) -> int:
    """Process a batch of DLQ messages with retry logic.

    Reads pending messages, checks if they're ready for retry (backoff elapsed),
    and either retries or marks as exhausted.

    Returns the number of messages processed.
    """
    client = get_redis_client()
    if client is None:
        return 0

    processed = 0
    try:
        messages = client.xread({DLQ_STREAM: "0"}, count=batch_size, block=0)
        if not messages:
            return 0

        for stream_name, entries in messages:
            for message_id, fields in entries:
                retry_count = int(fields.get("retry_count", 0))
                status = fields.get("status", "pending")

                if status == "exhausted":
                    continue

                if status == "retrying":
                    continue

                if retry_count >= MAX_RETRIES:
                    client.xadd(DLQ_STREAM, {
                        **fields,
                        "status": "exhausted",
                        "last_retry_at": str(time.time()),
                    })
                    client.xdel(DLQ_STREAM, message_id)
                    logger.warning(f"DLQ message {message_id} exhausted after {retry_count} retries")
                    processed += 1
                    continue

                now = time.time()
                created_at = float(fields.get("created_at", now))
                backoff = BASE_BACKOFF_SECONDS * (2 ** retry_count)

                if now - created_at < backoff:
                    continue

                client.xadd(DLQ_STREAM, {
                    **fields,
                    "retry_count": str(retry_count + 1),
                    "status": "retrying",
                    "last_retry_at": str(time.time()),
                })
                client.xdel(DLQ_STREAM, message_id)
                logger.info(f"Retrying DLQ message {message_id} (attempt {retry_count + 1}/{MAX_RETRIES})")
                processed += 1

    except Exception as e:
        logger.warning(f"Failed to process DLQ batch: {e}")

    return processed
