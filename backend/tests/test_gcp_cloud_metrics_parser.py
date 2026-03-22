import unittest
import tempfile
import os
import sqlite3

from backend.ingestion.parsers.gcp_cloud_metrics import GcpCloudMetricsParser


class TestGcpCloudMetricsParser(unittest.TestCase):
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
        self.parser = GcpCloudMetricsParser(db_path=self.db_path, batch_size=10)

    def tearDown(self):
        try:
            os.remove(self.db_path)
        except Exception:
            pass

    def test_gcp_good_and_bad_rows(self):
        with open('backend/Sample-Assets/Synthetic Data/gcp_cloud_metrics.csv', 'r') as f:
            lines = f.readlines()

        good = [lines[1].strip(), lines[3].strip()]
        for ln in good:
            self.assertTrue(self.parser.process_line(ln, source='CLOUD'))

        # bad row: missing metric value
        bad = '2026-03-05T09:00:00.000Z,synth-banking-sim-001,gke_container,terminal-handler-pod-xxx,europe-west2-b,container/cpu/usage_time,,s{CPU},'
        self.assertFalse(self.parser.process_line(bad, source='CLOUD'))

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
