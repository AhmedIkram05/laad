from backend.src.database.connection import get_conn, release_conn
from backend.src.ingestion.parsers.base_parser import BaseParser
from backend.tests.helpers import reset_test_db


class DummyParser(BaseParser):
    def parse_line(self, line: str):
        line = line.strip()
        if line == 'BAD':
            raise ValueError('malformed')
        return {'raw': line}


def test_good_line_buffers():
    reset_test_db()
    parser = DummyParser(batch_size=2)

    ok = parser.process_line('hello')
    assert ok is True
    assert len(parser._buffer) == 1


def test_bad_line_returns_false_and_error_recorded():
    reset_test_db()
    parser = DummyParser(batch_size=2)

    ok = parser.process_line('BAD')
    assert ok is False

    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT COUNT(*) FROM ingestion_errors')
            count = cur.fetchone()[0]
        assert count >= 1
    finally:
        release_conn(conn)
