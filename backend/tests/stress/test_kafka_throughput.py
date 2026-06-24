"""Kafka Throughput Stress Tests — validates producer/consumer throughput.

These tests use mocked Kafka (already autouse-mocked in conftest.py)
to measure the overhead of serialisation, deduplication, and message routing
without requiring a real Kafka broker.

In production, k6 or real Kafka load tests would validate actual broker throughput.
"""
from __future__ import annotations
import time
from unittest.mock import MagicMock, patch

import pytest

from backend.kafka.deduplicator import Deduplicator
from backend.src.ingestion.write_helper import write_batch


# Number of messages for throughput measurement
BATCH_SIZES = [100, 500]

# Acceptable throughput floor (messages/second) on mocked infrastructure
# These are sanity thresholds, not production benchmarks
MIN_THROUGHPUT = 1000  # msgs/sec


class TestKafkaProducerThroughput:
    """2 tests: producer throughput at different batch sizes."""

    @pytest.mark.parametrize("n_messages", BATCH_SIZES, ids=lambda n: f"{n}_messages")
    @patch("backend.kafka.producer.KafkaProducer")
    def test_producer_batch_throughput(self, mock_kafka_producer, n_messages):
        """Measure Kafka producer throughput with mocked broker.

        Validates that serialisation + message_id generation + topic routing
        overhead is within acceptable bounds.
        """
        from backend.kafka.producer import ATMProducer

        mock_instance = MagicMock()
        mock_kafka_producer.return_value = mock_instance

        producer = ATMProducer()

        messages = [
            {
                "source": "ATM_APP",
                "timestamp": "2026-01-15T10:00:00Z",
                "atm_id": f"ATM-{i % 10:03d}",
                "event_type": "transaction",
                "message": f"Test message {i}",
            }
            for i in range(n_messages)
        ]

        start = time.monotonic()
        for msg in messages:
            producer.send_event(msg)
        producer.flush()
        elapsed = time.monotonic() - start

        throughput = n_messages / elapsed if elapsed > 0 else float("inf")
        assert mock_instance.send.call_count == n_messages
        assert throughput >= MIN_THROUGHPUT, (
            f"Producer throughput too low: {throughput:.0f} msgs/sec "
            f"(sent {n_messages} in {elapsed:.3f}s)"
        )


class TestKafkaConsumerThroughput:
    """2 tests: deduplicator throughput at different batch sizes."""

    @pytest.mark.parametrize("n_messages", BATCH_SIZES, ids=lambda n: f"{n}_messages")
    def test_deduplicator_throughput(self, n_messages):
        """Measure deduplication throughput with hybrid LRU+Redis approach.

        This tests the in-memory LRU path (Redis mock returns False for
        SISMEMBER), which is the common-case fast path.
        """
        dedup = Deduplicator(max_size=10000)

        # Generate unique message IDs
        import uuid
        msg_ids = [str(uuid.uuid4()) for _ in range(n_messages)]

        # Measure mark + check throughput
        start = time.monotonic()
        for mid in msg_ids:
            dedup.mark_seen(mid)
            dedup.is_duplicate(mid)
        elapsed = time.monotonic() - start

        # Total operations = mark + check = 2 * n_messages
        total_ops = 2 * n_messages
        throughput = total_ops / elapsed if elapsed > 0 else float("inf")
        assert throughput >= MIN_THROUGHPUT, (
            f"Deduplicator throughput too low: {throughput:.0f} ops/sec "
            f"({total_ops} ops in {elapsed:.3f}s)"
        )
