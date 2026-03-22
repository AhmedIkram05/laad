import unittest
import tempfile
import os
import sqlite3

from backend.ingestion.parsers.prometheus import PrometheusParser


class TestPrometheusParser(unittest.TestCase):
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
        self.parser = PrometheusParser(db_path=self.db_path, batch_size=10)

    def tearDown(self):
        try:
            os.remove(self.db_path)
        except Exception:
            pass

    def test_prometheus_good_and_bad_rows(self):
        # Load a few lines from the sample CSV
        with open('backend/Sample-Assets/Synthetic Data/prometheus_metrics.csv', 'r') as f:
            lines = f.readlines()

        # Feed two good lines
        good_lines = [lines[1].strip(), lines[2].strip()]
        for ln in good_lines:
            ok = self.parser.process_line(ln, source='PROMETHEUS')
            self.assertTrue(ok)

        # Feed a bad/malformed line that should be rejected
        bad = 'not,a,valid,csv,line'
        ok = self.parser.process_line(bad, source='PROMETHEUS')
        self.assertFalse(ok)

        # Feed a malformed numeric value that should be sanitised (e.g. '890iembre')
        malformed_numeric = '2026-03-05T09:15:00Z,http_requests_total,counter,890iembre,auth,pod-1,cid,,prod,desc'
        ok = self.parser.process_line(malformed_numeric, source='PROMETHEUS')
        self.assertTrue(ok)

        # Flush and verify metrics rows and ingestion_errors
        self.parser.flush()
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute('SELECT COUNT(*) FROM metrics')
        metrics_count = cur.fetchone()[0]
        cur.execute('SELECT COUNT(*) FROM ingestion_errors')
        err_count = cur.fetchone()[0]
        conn.close()

        # two good lines + one sanitised malformed numeric
        self.assertEqual(metrics_count, len(good_lines) + 1)
        self.assertGreaterEqual(err_count, 1)


if __name__ == '__main__':
    unittest.main()
