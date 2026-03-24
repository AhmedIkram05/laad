import json
import os
import sqlite3
import tempfile
import unittest

from backend.ingestion.parsers.atm_app import AtmAppParser
from backend.ingestion.parsers.gcp_cloud_metrics import GcpCloudMetricsParser
from backend.ingestion.parsers.hardware_sensor import HardwareSensorParser
from backend.ingestion.parsers.kafka_metrics import KafkaMetricsParser
from backend.ingestion.parsers.prometheus import PrometheusParser
from backend.ingestion.parsers.terminal_handler import TerminalHandlerParser
from backend.ingestion.parsers.windows_os import WindowsOSParser


class TestIngestionIntegration(unittest.TestCase):
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

    def tearDown(self):
        try:
            os.remove(self.db_path)
        except Exception:
            pass

    def _feed_json(self, parser, path: str, source: str, max_records: int = 5) -> int:
        with open(path, 'r') as f:
            arr = json.load(f)

        accepted = 0
        for item in arr:
            if parser.process_line(json.dumps(item), source=source):
                accepted += 1
            # max_records == None or 0 -> unlimited
            if max_records and accepted >= max_records:
                break
        parser.flush()
        return accepted

    def _feed_csv(self, parser, path: str, source: str, max_records: int = 5) -> int:
        accepted = 0
        with open(path, 'r') as f:
            _ = f.readline()  # header
            for ln in f:
                ln = ln.strip()
                if not ln:
                    continue
                if parser.process_line(ln, source=source):
                    accepted += 1
                # max_records == None or 0 -> unlimited
                if max_records and accepted >= max_records:
                    break
        parser.flush()
        return accepted

    def test_end_to_end_ingestion_sample(self):
        base = os.environ.get('TEST_DATA_DIR')
        if not base:
            raise RuntimeError('TEST_DATA_DIR is not set; tests expect generated dataset to be available via the seeded fixture')
        sources = [
            ('atm_app', AtmAppParser, os.path.join(base, 'atm_application_log.json'), 'ATM_APP', 'json'),
            ('hardware', HardwareSensorParser, os.path.join(base, 'atm_hardware_sensor_log.json'), 'HARDWARE', 'json'),
            ('terminal', TerminalHandlerParser, os.path.join(base, 'terminal_handler_app_log.json'), 'TERMINAL_HANDLER', 'json'),
            ('kafka', KafkaMetricsParser, os.path.join(base, 'kafka_atm_metrics_stream.json'), 'KAFKA', 'json'),
            ('prometheus', PrometheusParser, os.path.join(base, 'prometheus_metrics.csv'), 'PROMETHEUS', 'csv'),
            ('windows', WindowsOSParser, os.path.join(base, 'windows_os_metrics.csv'), 'OS', 'csv'),
            ('gcp', GcpCloudMetricsParser, os.path.join(base, 'gcp_cloud_metrics.csv'), 'CLOUD', 'csv'),
        ]

        # Opt-in full ingest via env var `FULL_INGEST` (truthy) to process entire files.
        full = os.getenv('FULL_INGEST')
        max_records = None if full else 5

        accepted_by_source = {}
        for name, parser_cls, path, source, kind in sources:
            parser = parser_cls(db_path=self.db_path, batch_size=10)
            if kind == 'json':
                accepted = self._feed_json(parser, path, source, max_records=max_records)
            else:
                accepted = self._feed_csv(parser, path, source, max_records=max_records)
            accepted_by_source[name] = accepted

        for name, accepted in accepted_by_source.items():
            self.assertGreater(accepted, 0, f'No rows ingested for {name}')

        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute('SELECT COUNT(*) FROM events')
        events_rows = cur.fetchone()[0]
        cur.execute('SELECT COUNT(*) FROM metrics')
        metrics_rows = cur.fetchone()[0]
        cur.execute('SELECT COUNT(*) FROM ingestion_errors')
        errors_rows = cur.fetchone()[0]
        conn.close()

        self.assertGreater(events_rows, 0)
        self.assertGreater(metrics_rows, 0)
        self.assertGreaterEqual(errors_rows, 0)


if __name__ == '__main__':
    unittest.main()