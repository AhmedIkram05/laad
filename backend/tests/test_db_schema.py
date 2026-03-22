import unittest
from pathlib import Path
import sqlite3


class TestDBSchema(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(':memory:')
        self.cur = self.conn.cursor()

        schema_file = Path(__file__).resolve().parents[1] / 'database' / 'schema.sql'
        if not schema_file.exists():
            self.skipTest('database/schema.sql not found')

        with open(schema_file, 'r', encoding='utf-8') as fh:
            self.cur.executescript(fh.read())
            self.conn.commit()

    def tearDown(self):
        try:
            self.conn.close()
        except Exception:
            pass

    def test_tables_exist(self):
        self.cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [r[0] for r in self.cur.fetchall()]

        expected_tables = ['atms', 'events', 'metrics', 'anomalies', 'recommendations', 'feedback', 'ingestion_errors']
        for t in expected_tables:
            self.assertIn(t, tables, f"Table {t} should exist in schema.")

    def test_events_columns(self):
        self.cur.execute("PRAGMA table_info(events);")
        cols = [r[1] for r in self.cur.fetchall()]
        self.assertIn('transaction_id', cols)
        self.assertIn('correlation_id', cols)

    def test_anomalies_columns(self):
        self.cur.execute("PRAGMA table_info(anomalies);")
        cols = [r[1] for r in self.cur.fetchall()]
        self.assertNotIn('feedback_rating', cols)
        self.assertNotIn('recommended_action', cols)
        self.assertIn('evidence_event_ids', cols)
        self.assertIn('evidence_metric_ids', cols)
        self.assertIn('model_confidence_score', cols)


if __name__ == '__main__':
    unittest.main()
