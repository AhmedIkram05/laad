"""Concurrency tests for generator writes (Kafka producer-based).

Simulates multiple emitters running concurrently, verifying that the
producer interface handles concurrent calls gracefully.
"""
from __future__ import annotations
import pytest
import threading
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

from backend.generator.continuous_generator import emit_tick


def _mock_producer():
    return MagicMock()


def test_concurrent_writes():
    mock = _mock_producer()
    t = datetime.now(timezone.utc)
    anomaly_last = {}

    def worker():
        emit_tick(mock, t, anomaly_last)

    threads = [threading.Thread(target=worker) for _ in range(5)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()

    assert mock.flush.call_count == 5