"""Concurrency tests for generator writes."""
import pytest
import threading
from backend.generator.continuous_generator import emit_tick
from datetime import datetime, timezone

def test_concurrent_writes():
    """Simulate multiple emitters running concurrently."""
    t = datetime.now(timezone.utc)
    anomaly_last = {}
    
    def worker():
        try:
            emit_tick(t, anomaly_last)
        except:
            pass

    threads = [threading.Thread(target=worker) for _ in range(5)]
    for th in threads: th.start()
    for th in threads: th.join()
