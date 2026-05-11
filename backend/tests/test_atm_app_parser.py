import json

from backend.src.database.connection import get_conn, release_conn
from backend.src.ingestion.parsers.atm_app import AtmAppParser
from backend.tests.helpers import reset_test_db, sample_path


def test_parse_and_flush_sample():
    reset_test_db()
    parser = AtmAppParser(batch_size=10)

    with open(sample_path('atm_application_log.json'), 'r', encoding='utf-8') as f:
        arr = json.load(f)

    for item in arr[:3]:
        parser.process_line(json.dumps(item), source='ATM_APP')

    parser.flush()

    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT COUNT(*) FROM events')
            count = cur.fetchone()[0]
        assert count == 3
    finally:
        release_conn(conn)
