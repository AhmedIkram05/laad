import json

from backend.src.database.connection import get_conn, release_conn
from backend.src.ingestion.parsers.terminal_handler import TerminalHandlerParser
from backend.tests.helpers import reset_test_db, sample_path


def test_terminal_good_and_bad_rows():
    reset_test_db()
    parser = TerminalHandlerParser(batch_size=10)

    with open(sample_path("terminal_handler_app_log.json"), "r", encoding="utf-8") as f:
        arr = json.load(f)

    good = [json.dumps(arr[0]), json.dumps(arr[1])]
    for line in good:
        assert parser.process_line(line, source="TERMINAL_HANDLER") is True

    assert parser.process_line("{not: valid json}", source="TERMINAL_HANDLER") is False

    parser.flush()

    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM events")
            events_count = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM ingestion_errors")
            error_count = cur.fetchone()[0]
        assert events_count == len(good)
        assert error_count >= 1
    finally:
        release_conn(conn)
