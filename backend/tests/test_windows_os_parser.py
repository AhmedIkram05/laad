import unittest
import tempfile
import os
import sqlite3
import os

from backend.ingestion.parsers.windows_os import WindowsOSParser
from backend.tests.helpers import sample_path


class TestWindowsOSParser(unittest.TestCase):
    def setUp(self):
        fd, path = tempfile.mkstemp(prefix='test_db_', suffix='.sqlite')
        os.close(fd)
        self.db_path = path
        with open('backend/database/schema.sql', 'r') as f:
            schema = f.read()
        conn = sqlite3.connect(self.db_path)
        conn.executescript(schema)
        conn.commit()
        conn.close()
        self.parser = WindowsOSParser(db_path=self.db_path, batch_size=10)

    def tearDown(self):
        try:
            os.remove(self.db_path)
        except Exception:
            pass

    def test_windows_good_and_bad_rows(self):
        with open(sample_path('windows_os_metrics.csv'), 'r') as f:
            lines = f.readlines()

        # use two good lines
        good = [lines[1].strip(), lines[2].strip()]
        for ln in good:
            self.assertTrue(self.parser.process_line(ln, source='OS'))

        # malformed row (incomplete)
        bad = '2026-03-05T09:00:00.000Z,ATM-GB-XXXX'
        self.assertFalse(self.parser.process_line(bad, source='OS'))

        self.parser.flush()
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute('SELECT COUNT(*) FROM metrics')
        mcount = cur.fetchone()[0]
        cur.execute('SELECT COUNT(*) FROM ingestion_errors')
        ecount = cur.fetchone()[0]
        conn.close()

        self.assertEqual(mcount, len(good))
        self.assertGreaterEqual(ecount, 1)


if __name__ == '__main__':
    unittest.main()
