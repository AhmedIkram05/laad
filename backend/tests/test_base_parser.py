import unittest
import tempfile
import os
import sqlite3

from backend.src.ingestion.parsers.base_parser import BaseParser


class DummyParser(BaseParser):
    def parse_line(self, line: str):
        line = line.strip()
        if line == 'BAD':
            raise ValueError('malformed')
        return {'raw': line}


class TestBaseParser(unittest.TestCase):
    def setUp(self):
        # Create a temporary on-disk sqlite DB so parser's separate connections
        # can see the same schema and tables. Initialise schema for tests.
        fd, path = tempfile.mkstemp(prefix='test_db_', suffix='.sqlite')
        os.close(fd)
        self.test_db_path = path

        # Execute project schema into the temp DB
        with open('backend/src/database/schema.sql', 'r') as f:
            schema = f.read()
        conn = sqlite3.connect(self.test_db_path)
        try:
            conn.executescript(schema)
            conn.commit()
        finally:
            conn.close()

        self.parser = DummyParser(db_path=self.test_db_path, batch_size=2)

    def tearDown(self):
        try:
            os.remove(self.test_db_path)
        except OSError:
            pass

    def test_good_line_buffers(self):
        ok = self.parser.process_line('hello')
        self.assertTrue(ok)
        self.assertEqual(len(self.parser._buffer), 1)

    def test_bad_line_returns_false_and_error_recorded(self):
        ok = self.parser.process_line('BAD')
        self.assertFalse(ok)

        # Confirm an ingestion_errors row was written
        conn = sqlite3.connect(self.test_db_path)
        try:
            cur = conn.cursor()
            cur.execute('SELECT COUNT(*) FROM ingestion_errors')
            count = cur.fetchone()[0]
            self.assertGreaterEqual(count, 1)
        finally:
            conn.close()


if __name__ == '__main__':
    unittest.main()
