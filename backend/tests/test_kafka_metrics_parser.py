import unittest
import tempfile
import os
import sqlite3
import json
import os

from backend.src.ingestion.parsers.kafka_metrics import KafkaMetricsParser
from backend.tests.helpers import sample_path


class TestKafkaMetricsParser(unittest.TestCase):
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
        self.parser = KafkaMetricsParser(db_path=self.db_path, batch_size=10)

    def tearDown(self):
        try:
            os.remove(self.db_path)
        except Exception:
            pass

    def test_kafka_good_and_bad_rows(self):
        with open(sample_path('kafka_atm_metrics_stream.json'), 'r') as f:
            arr = json.load(f)

        good = [json.dumps(arr[0]), json.dumps(arr[1])]
        for ln in good:
            self.assertTrue(self.parser.process_line(ln, source='KAFKA'))

        # bad: remove both primary and fallback metric keys to force failure
        bad_obj = dict(arr[0])
        bad_obj.pop('transaction_rate_tps', None)
        bad_obj.pop('response_time_ms', None)
        bad = json.dumps(bad_obj)
        self.assertFalse(self.parser.process_line(bad, source='KAFKA'))

        self.parser.flush()
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute('SELECT COUNT(*) FROM metrics')
        mcount = cur.fetchone()[0]
        cur.execute('SELECT COUNT(*) FROM ingestion_errors')
        err = cur.fetchone()[0]
        conn.close()

        self.assertEqual(mcount, len(good))
        self.assertGreaterEqual(err, 1)


if __name__ == '__main__':
    unittest.main()
