from datetime import datetime, timedelta, timezone

import pytest
from psycopg2.extras import Json

from backend.src.admin import cleanup as cleanup_mod
from backend.src.database.connection import get_conn, release_conn
from backend.tests.helpers import reset_test_db


def _insert_sample_rows(
    retention_days: int = 1, old_count: int = 3, new_count: int = 2
):
    conn = get_conn()
    try:
        now = datetime.now(timezone.utc)
        old_ts = now - timedelta(days=retention_days + 1)
        new_ts = now

        with conn.cursor() as cur:
            for i in range(old_count):
                cur.execute(
                    "INSERT INTO events (timestamp, source, message, payload) VALUES (%s, 'ATM_APP', %s, %s)",
                    (old_ts, f"old event {i}", Json({})),
                )
            for i in range(new_count):
                cur.execute(
                    "INSERT INTO events (timestamp, source, message, payload) VALUES (%s, 'ATM_APP', %s, %s)",
                    (new_ts, f"new event {i}", Json({})),
                )

            for _ in range(old_count):
                cur.execute(
                    "INSERT INTO metrics (timestamp, source, entity_id, metric_name, metric_value, payload) VALUES (%s, 'OS', 'ATM-GB-0001', 'cpu', 1.0, %s)",
                    (old_ts, Json({})),
                )
            for _ in range(new_count):
                cur.execute(
                    "INSERT INTO metrics (timestamp, source, entity_id, metric_name, metric_value, payload) VALUES (%s, 'OS', 'ATM-GB-0001', 'cpu', 1.0, %s)",
                    (new_ts, Json({})),
                )

            for i in range(old_count):
                cur.execute(
                    "INSERT INTO anomalies (detected_at, anomaly_type, severity, title, explanation, is_active) VALUES (%s, 'A1', 'HIGH', %s, %s, 0)",
                    (old_ts, f"old anomaly {i}", "ex"),
                )
            for i in range(new_count):
                cur.execute(
                    "INSERT INTO anomalies (detected_at, anomaly_type, severity, title, explanation) VALUES (%s, 'A1', 'HIGH', %s, %s)",
                    (new_ts, f"new anomaly {i}", "ex"),
                )

            for i in range(old_count):
                cur.execute(
                    "INSERT INTO ingestion_errors (timestamp, source, error_detail) VALUES (%s, 'INGEST', %s)",
                    (old_ts, f"err {i}"),
                )
            for i in range(new_count):
                cur.execute(
                    "INSERT INTO ingestion_errors (timestamp, source, error_detail) VALUES (%s, 'INGEST', %s)",
                    (new_ts, f"err new {i}"),
                )
        conn.commit()
    finally:
        release_conn(conn)


@pytest.mark.parametrize("retention_days", [1])
def test_run_cleanup_deletes_old_rows(retention_days):
    reset_test_db()

    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE retention_config SET retention_days = %s WHERE id = 1",
                (retention_days,),
            )
        conn.commit()
    finally:
        release_conn(conn)

    _insert_sample_rows(retention_days=retention_days, old_count=3, new_count=2)

    result = cleanup_mod.run_cleanup()

    assert result["retention_days"] == retention_days
    for table, _, _ in cleanup_mod.TABLE_CONFIG:
        assert table in result["deleted"]
        assert result["deleted"][table] >= 1

    conn2 = get_conn()
    try:
        with conn2.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM events")
            rows = cur.fetchone()[0]
        assert rows == 2
    finally:
        release_conn(conn2)


def test_run_cleanup_defaults_to_7_when_no_config():
    reset_test_db()

    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM retention_config WHERE id = 1")
            old_ts = datetime.now(timezone.utc) - timedelta(days=31)
            cur.execute(
                "INSERT INTO events (timestamp, source, message, payload) VALUES (%s, 'ATM_APP', 'old', %s)",
                (old_ts, Json({})),
            )
        conn.commit()
    finally:
        release_conn(conn)

    result = cleanup_mod.run_cleanup()
    assert result["retention_days"] == 7


def test_batched_delete_commits_between_batches(monkeypatch):
    reset_test_db()

    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE retention_config SET retention_days = 1 WHERE id = 1")

            old_ts = datetime.now(timezone.utc) - timedelta(days=2)
            for i in range(7):
                cur.execute(
                    "INSERT INTO events (timestamp, source, message, payload) VALUES (%s, 'ATM_APP', %s, %s)",
                    (old_ts, f"old {i}", Json({})),
                )
        conn.commit()
    finally:
        release_conn(conn)

    monkeypatch.setattr(cleanup_mod, "BATCH_SIZE", 2)

    result = cleanup_mod.run_cleanup()
    assert result["deleted"]["events"] == 7
