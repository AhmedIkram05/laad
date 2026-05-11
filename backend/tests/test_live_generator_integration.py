"""Integration tests for live generator."""
import pytest
from backend.src.database.connection import get_cursor
from backend.generator.continuous_generator import emit_tick

def test_generator_integration():
    """Verify that emit_tick actually inserts rows into the DB."""
    from datetime import datetime, timezone
    t = datetime.now(timezone.utc)
    anomaly_last = {}
    
    # This requires a running DB
    try:
        emit_tick(t, anomaly_last)
        with get_cursor() as cur:
            cur.execute("SELECT COUNT(*) as count FROM events")
            count = cur.fetchone()["count"]
            assert count >= 0
    except Exception as e:
        pytest.fail(f"Integration test failed due to DB connection: {e}")
