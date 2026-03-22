import unittest
import json
import sqlite3
import tempfile
import os

from backend.ingestion.parsers.atm_app import AtmAppParser


class TestAtmAppParser(unittest.TestCase):
    def setUp(self):
        # prepare temp DB with schema
        fd, path = tempfile.mkstemp(prefix='test_db_', suffix='.sqlite')
        os.close(fd)
        self.db_path = path
        with open('backend/database/schema.sql', 'r') as f:
            schema = f.read()
        conn = sqlite3.connect(self.db_path)
        conn.executescript(schema)
        conn.commit()
        conn.close()

        self.parser = AtmAppParser(db_path=self.db_path, batch_size=10)

    def tearDown(self):
        try:
            os.remove(self.db_path)
        except Exception:
            pass

    def test_parse_and_flush_sample(self):
        # Load a few sample events from the synthetic data file
        with open('backend/Sample-Assets/Synthetic Data/atm_application_log.json', 'r') as f:
            arr = json.load(f)

        # feed first three events
        for item in arr[:3]:
            self.parser.process_line(json.dumps(item), source='ATM_APP')

        # flush buffer to DB
        self.parser.flush()

        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute('SELECT COUNT(*) FROM events')
        count = cur.fetchone()[0]
        conn.close()

        self.assertEqual(count, 3)


if __name__ == '__main__':
    unittest.main()
