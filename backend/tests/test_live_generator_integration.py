"""Integration tests for live generator."""
import pytest
from backend.src.database.connection import get_cursor
from backend.generator.continuous_generator import emit_tick

def test_generator_integration():
    """Verify that emit_tick actually inserts rows into the DB."""
    from datetime import datetime, timezone
    t = datetime.now(timezone.utc)
    anomaly_last = {}

    try:
        with get_cursor() as cur:
            cur.execute("SELECT COUNT(*) as count FROM events")
            count_before = cur.fetchone()["count"]

        emit_tick(t, anomaly_last)

        with get_cursor() as cur:
            cur.execute("SELECT COUNT(*) as count FROM events")
            count_after = cur.fetchone()["count"]

        assert count_after > count_before, f"Expected rows to be inserted, but count_before={count_before}, count_after={count_after}"
    except Exception as e:
        pytest.fail(f"Integration test failed due to DB connection: {e}")
