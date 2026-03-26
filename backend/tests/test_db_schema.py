import unittest
from pathlib import Path
import sqlite3


class TestDBSchema(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(':memory:')
        self.cur = self.conn.cursor()

        schema_file = Path(__file__).resolve().parents[1] / 'src' / 'database' / 'schema.sql'
        if not schema_file.exists():
            self.skipTest('src.database/schema.sql not found')

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

        expected_tables = ['atms', 'events', 'metrics', 'anomalies', 'ingestion_errors']
        for t in expected_tables:
            self.assertIn(t, tables, f"Table {t} should exist in schema.")

    def test_events_columns(self):
        self.cur.execute("PRAGMA table_info(events);")
        cols = [r[1] for r in self.cur.fetchall()]
        self.assertIn('transaction_id', cols)
        self.assertIn('correlation_id', cols)

    def test_atms_columns(self):
        self.cur.execute("PRAGMA table_info(atms);")
        cols = [r[1] for r in self.cur.fetchall()]
        self.assertIn('os_version', cols)

    def test_anomalies_columns(self):
        self.cur.execute("PRAGMA table_info(anomalies);")
        cols = [r[1] for r in self.cur.fetchall()]
        self.assertIn('feedback_rating', cols)
        self.assertIn('recommended_action', cols)
        self.assertNotIn('evidence_event_ids', cols)
        self.assertNotIn('evidence_metric_ids', cols)
        self.assertIn('model_confidence_score', cols)

    def test_unified_view_columns(self):
        # Ensure the unified analysis view exposes recognised fields
        try:
            self.cur.execute("SELECT * FROM v_unified_analysis LIMIT 0;")
        except Exception:
            self.skipTest('v_unified_analysis view not present')

        cols = [d[0] for d in self.cur.description]
        expected_view_cols = ['atm_id', 'atm_status', 'component', 'error_code', 'error_detail', 'correlation_id']
        for c in expected_view_cols:
            self.assertIn(c, cols, f"Unified view should expose canonical column {c}")


if __name__ == '__main__':
    unittest.main()
