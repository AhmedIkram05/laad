import json

from backend.src.database.connection import get_conn, release_conn
from backend.src.ingestion.parsers.hardware_sensor import HardwareSensorParser
from backend.tests.helpers import reset_test_db, sample_path


def test_hardware_good_and_bad_rows():
    reset_test_db()
    parser = HardwareSensorParser(batch_size=10)

    with open(sample_path('atm_hardware_sensor_log.json'), 'r', encoding='utf-8') as f:
        arr = json.load(f)

    good = [json.dumps(arr[0]), json.dumps(arr[1])]
    for line in good:
        assert parser.process_line(line, source='HARDWARE') is True

    assert parser.process_line('', source='HARDWARE') is False

    parser.flush()

    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT COUNT(*) FROM events')
            events_count = cur.fetchone()[0]
            cur.execute('SELECT COUNT(*) FROM ingestion_errors')
            error_count = cur.fetchone()[0]
        assert events_count == len(good)
        assert error_count >= 1
    finally:
        release_conn(conn)
