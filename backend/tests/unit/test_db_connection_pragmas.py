import queue
import threading
from datetime import datetime, timezone

from psycopg2.extras import Json

from backend.src.database.connection import get_conn, release_conn
from backend.tests.helpers import reset_test_db


def test_get_conn_allows_cross_thread_write_via_pool():
    reset_test_db()
    errors = queue.Queue()

    def thread_writer():
        conn = get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO events (timestamp, source, message, payload) VALUES (%s, 'TEST', %s, %s)",
                    (datetime.now(timezone.utc), "t1", Json({})),
                )
            conn.commit()
            errors.put(None)
        except Exception as exc:
            errors.put(exc)
        finally:
            release_conn(conn)

    t = threading.Thread(target=thread_writer)
    t.start()
    t.join(timeout=5)

    result = errors.get_nowait()
    if result is not None:
        raise result

    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM events")
            rows = cur.fetchone()[0]
        assert rows >= 1
    finally:
        release_conn(conn)
