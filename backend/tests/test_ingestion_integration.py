import json
import os

from backend.src.database.connection import get_conn, release_conn
from backend.src.ingestion.parsers.atm_app import AtmAppParser
from backend.src.ingestion.parsers.gcp_cloud_metrics import GcpCloudMetricsParser
from backend.src.ingestion.parsers.hardware_sensor import HardwareSensorParser
from backend.src.ingestion.parsers.kafka_metrics import KafkaMetricsParser
from backend.src.ingestion.parsers.prometheus import PrometheusParser
from backend.src.ingestion.parsers.terminal_handler import TerminalHandlerParser
from backend.src.ingestion.parsers.windows_os import WindowsOSParser
from backend.tests.helpers import reset_test_db


def _feed_json(parser, path: str, source: str, max_records: int = 5) -> int:
    with open(path, "r", encoding="utf-8") as f:
        arr = json.load(f)

    accepted = 0
    for item in arr:
        if parser.process_line(json.dumps(item), source=source):
            accepted += 1
        if max_records and accepted >= max_records:
            break
    parser.flush()
    return accepted


def _feed_csv(parser, path: str, source: str, max_records: int = 5) -> int:
    accepted = 0
    with open(path, "r", encoding="utf-8") as f:
        _ = f.readline()
        for line in f:
            line = line.strip()
            if not line:
                continue
            if parser.process_line(line, source=source):
                accepted += 1
            if max_records and accepted >= max_records:
                break
    parser.flush()
    return accepted


def test_end_to_end_ingestion_sample():
    reset_test_db()

    base = os.environ.get("TEST_DATA_DIR")
    if not base:
        raise RuntimeError(
            "TEST_DATA_DIR is not set; tests expect generated dataset to be available via the seeded fixture"
        )

    sources = [
        (
            "atm_app",
            AtmAppParser,
            os.path.join(base, "atm_application_log.json"),
            "ATM_APP",
            "json",
        ),
        (
            "hardware",
            HardwareSensorParser,
            os.path.join(base, "atm_hardware_sensor_log.json"),
            "HARDWARE",
            "json",
        ),
        (
            "terminal",
            TerminalHandlerParser,
            os.path.join(base, "terminal_handler_app_log.json"),
            "TERMINAL_HANDLER",
            "json",
        ),
        (
            "kafka",
            KafkaMetricsParser,
            os.path.join(base, "kafka_atm_metrics_stream.json"),
            "KAFKA",
            "json",
        ),
        (
            "prometheus",
            PrometheusParser,
            os.path.join(base, "prometheus_metrics.csv"),
            "PROMETHEUS",
            "csv",
        ),
        (
            "windows",
            WindowsOSParser,
            os.path.join(base, "windows_os_metrics.csv"),
            "OS",
            "csv",
        ),
        (
            "gcp",
            GcpCloudMetricsParser,
            os.path.join(base, "gcp_cloud_metrics.csv"),
            "CLOUD",
            "csv",
        ),
    ]

    full = os.getenv("FULL_INGEST")
    max_records = None if full else 5

    accepted_by_source = {}
    for name, parser_cls, path, source, kind in sources:
        parser = parser_cls(batch_size=10)
        if kind == "json":
            accepted = _feed_json(parser, path, source, max_records=max_records)
        else:
            accepted = _feed_csv(parser, path, source, max_records=max_records)
        accepted_by_source[name] = accepted

    for name, accepted in accepted_by_source.items():
        assert accepted > 0, f"No rows ingested for {name}"

    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM events")
            events_rows = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM metrics")
            metrics_rows = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM ingestion_errors")
            errors_rows = cur.fetchone()[0]

        assert events_rows > 0
        assert metrics_rows > 0
        assert errors_rows >= 0
    finally:
        release_conn(conn)
