from backend.src.database.connection import get_conn, release_conn
from backend.src.ingestion.parsers.prometheus import PrometheusParser
from backend.tests.helpers import reset_test_db, sample_path


def test_prometheus_good_and_bad_rows():
    reset_test_db()
    parser = PrometheusParser(batch_size=10)

    with open(sample_path('prometheus_metrics.csv'), 'r', encoding='utf-8') as f:
        lines = f.readlines()

    good_lines = [lines[1].strip(), lines[2].strip()]
    for line in good_lines:
        assert parser.process_line(line, source='PROMETHEUS') is True

    assert parser.process_line('not,a,valid,csv,line', source='PROMETHEUS') is False

    malformed_numeric = '2026-03-05T09:15:00Z,http_requests_total,counter,890iembre,auth,pod-1,cid,,prod,desc'
    assert parser.process_line(malformed_numeric, source='PROMETHEUS') is False

    parser.flush()

    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT COUNT(*) FROM metrics')
            metrics_count = cur.fetchone()[0]
            cur.execute('SELECT COUNT(*) FROM ingestion_errors')
            error_count = cur.fetchone()[0]
        assert metrics_count == len(good_lines)
        assert error_count >= 1
    finally:
        release_conn(conn)
