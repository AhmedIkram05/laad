from backend.src.database.connection import get_conn, release_conn
from backend.src.ingestion.parsers.windows_os import WindowsOSParser
from backend.tests.helpers import reset_test_db, sample_path


def test_windows_good_and_bad_rows():
    reset_test_db()
    parser = WindowsOSParser(batch_size=10)

    with open(sample_path("windows_os_metrics.csv"), "r", encoding="utf-8") as f:
        lines = f.readlines()

    good = [lines[1].strip(), lines[2].strip()]
    for line in good:
        assert parser.process_line(line, source="OS") is True

    bad = "2026-03-05T09:00:00.000Z,ATM-GB-XXXX"
    assert parser.process_line(bad, source="OS") is False

    parser.flush()

    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM metrics")
            metric_count = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM ingestion_errors")
            error_count = cur.fetchone()[0]
        assert metric_count == len(good)
        assert error_count >= 1
    finally:
        release_conn(conn)
