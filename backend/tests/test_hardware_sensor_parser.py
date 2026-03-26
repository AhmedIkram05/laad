import unittest
import tempfile
import os
import sqlite3
import json
import os

from backend.src.ingestion.parsers.hardware_sensor import HardwareSensorParser
from backend.tests.helpers import sample_path


class TestHardwareSensorParser(unittest.TestCase):
    def setUp(self):
        fd, path = tempfile.mkstemp(prefix='test_db_', suffix='.sqlite')
        os.close(fd)
        self.db_path = path
        with open('backend/src/database/schema.sql', 'r') as f:
            schema = f.read()
        conn = sqlite3.connect(self.db_path)
        conn.executescript(schema)
        conn.commit()
        conn.close()
        self.parser = HardwareSensorParser(db_path=self.db_path, batch_size=10)

    def tearDown(self):
        try:
            os.remove(self.db_path)
        except Exception:
            pass

    def test_hardware_good_and_bad_rows(self):
        with open(sample_path('atm_hardware_sensor_log.json'), 'r') as f:
            arr = json.load(f)

        good = [json.dumps(arr[0]), json.dumps(arr[1])]
        for ln in good:
            self.assertTrue(self.parser.process_line(ln, source='HARDWARE'))

        # bad: missing required fields / malformed JSON
        bad = ''
        self.assertFalse(self.parser.process_line(bad, source='HARDWARE'))

        self.parser.flush()
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute('SELECT COUNT(*) FROM events')
        ecount = cur.fetchone()[0]
        cur.execute('SELECT COUNT(*) FROM ingestion_errors')
        err = cur.fetchone()[0]
        conn.close()

        self.assertEqual(ecount, len(good))
        self.assertGreaterEqual(err, 1)


if __name__ == '__main__':
    unittest.main()
