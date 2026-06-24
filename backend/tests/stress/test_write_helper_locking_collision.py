import threading
from datetime import datetime, timezone

from psycopg2.extras import Json

from backend.src.database.connection import get_conn, release_conn
from backend.src.ingestion.write_helper import write_batch
from backend.tests.helpers import reset_test_db


def test_write_helper_handles_concurrent_writes():
    reset_test_db()

    sql = "INSERT INTO events (timestamp, source, message, payload) VALUES %s"

    holder = get_conn()
    writer = get_conn()

    try:

        def holder_write():
            write_batch(
                holder,
                sql,
                [(datetime.now(timezone.utc), "ATM_APP", "holder", Json({}))],
                retries=10,
                backoff_base=0.01,
                backoff_max=0.05,
            )

        t = threading.Thread(target=holder_write)
        t.start()

        write_batch(
            writer,
            sql,
            [(datetime.now(timezone.utc), "ATM_APP", "writer", Json({}))],
            retries=10,
            backoff_base=0.01,
            backoff_max=0.05,
        )

        t.join(timeout=5)

        verifier = get_conn()
        try:
            with verifier.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM events")
                count = cur.fetchone()[0]
            assert count >= 2
        finally:
            release_conn(verifier)
    finally:
        release_conn(holder)
        release_conn(writer)
