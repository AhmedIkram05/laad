import os
import sqlite3
import unittest
import tempfile
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from datetime import datetime, timezone

from backend.src.ingestion.parsers.base_parser import EventDataParser, MetricDataParser
import backend.src.database.init_db as init_db


class EventProducer(EventDataParser):
    def __init__(self, producer_id: int, db_path: str, batch_size: int = 100):
        super().__init__(db_path=db_path, batch_size=batch_size)
        self._producer_id = producer_id

    def parse_line(self, line: str):
        idx = int(line)
        return {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'source': f'EVT_{self._producer_id}',
            'atm_id': f'atm_{self._producer_id}',
            'correlation_id': f'c_{self._producer_id}_{idx}',
            'transaction_id': f't_{self._producer_id}_{idx}',
            'event_type': 'TEST',
            'severity': 'INFO',
            'message': 'ok',
            'payload': '{}',
        }


class MetricProducer(MetricDataParser):
    def __init__(self, producer_id: int, db_path: str, batch_size: int = 100):
        super().__init__(db_path=db_path, batch_size=batch_size)
        self._producer_id = producer_id

    def parse_line(self, line: str):
        idx = int(line)
        return {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'source': f'MET_{self._producer_id}',
            'entity_id': f'entity_{self._producer_id}',
            'metric_name': 'm_test',
            'metric_value': float(idx % 100),
            'payload': '{}',
        }


class ConcurrencySmokeTest(unittest.TestCase):
    def setUp(self):
        # Create a temporary directory for the test DB so tests don't write
        # to the repository root. Use mkdtemp so we can remove it in tearDown.
        self._temp_dir = Path(tempfile.mkdtemp(prefix="testdb_"))
        self.db_name = 'concurrent_test.db'
        self.db_path = self._temp_dir / self.db_name
        try:
            self.db_path.touch(exist_ok=True)
        except Exception:
            pass

        # Apply schema directly to the test DB to ensure tables exist
        # Locate schema next to the database package to be robust across cwd
        schema_file = Path(init_db.__file__).resolve().parent / 'schema.sql'
        try:
            with open(schema_file, 'r') as f:
                schema_sql = f.read()
        except FileNotFoundError:
            self.skipTest('Schema file not found')

        try:
            from backend.src.database.connection import get_db
            conn = get_db(str(self.db_path))
            cur = conn.cursor()
            cur.executescript(schema_sql)

            conn.commit()
            conn.close()
        except Exception as e:
            self.skipTest(f'Unable to initialise test DB: {e}')

    def tearDown(self):
        try:
            # remove the DB file and temp directory
            if self.db_path.exists():
                os.remove(self.db_path)
        except Exception:
            pass
        try:
            shutil.rmtree(self._temp_dir)
        except Exception:
            pass

    def test_concurrent_writes(self):
        # Spawn multiple producer threads that each insert rows concurrently
        num_event_producers = 3
        num_metric_producers = 3
        rows_per_producer = 500

        def run_event(p_id):
            p = EventProducer(p_id, db_path=str(self.db_path), batch_size=50)
            for i in range(rows_per_producer):
                p.process_line(str(i))
            p.flush()

        def run_metric(p_id):
            p = MetricProducer(p_id, db_path=str(self.db_path), batch_size=50)
            for i in range(rows_per_producer):
                p.process_line(str(i))
            p.flush()

        with ThreadPoolExecutor(max_workers=6) as ex:
            futures = []
            for i in range(num_event_producers):
                futures.append(ex.submit(run_event, i))
            for i in range(num_metric_producers):
                futures.append(ex.submit(run_metric, i))
            for f in futures:
                f.result()

        # Verify counts
        con = sqlite3.connect(str(self.db_path))
        cur = con.cursor()
        cur.execute('SELECT COUNT(*) FROM events')
        events = cur.fetchone()[0]
        cur.execute('SELECT COUNT(*) FROM metrics')
        metrics = cur.fetchone()[0]
        cur.execute('SELECT COUNT(*) FROM ingestion_errors')
        errors = cur.fetchone()[0]
        con.close()

        self.assertEqual(events, num_event_producers * rows_per_producer)
        self.assertEqual(metrics, num_metric_producers * rows_per_producer)
        self.assertEqual(errors, 0, 'No ingestion errors expected under concurrent load')


if __name__ == '__main__':
    unittest.main()
