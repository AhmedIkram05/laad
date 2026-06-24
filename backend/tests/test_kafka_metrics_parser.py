import json

from backend.src.database.connection import get_conn, release_conn
from backend.src.ingestion.parsers.kafka_metrics import KafkaMetricsParser
from backend.tests.helpers import reset_test_db, sample_path


def test_kafka_good_and_bad_rows():
    reset_test_db()
    parser = KafkaMetricsParser(batch_size=10)

    with open(sample_path("kafka_atm_metrics_stream.json"), "r", encoding="utf-8") as f:
        arr = json.load(f)

    good = [json.dumps(arr[0]), json.dumps(arr[1])]
    for line in good:
        assert parser.process_line(line, source="KAFKA") is True

    bad_obj = dict(arr[0])
    bad_obj.pop("transaction_rate_tps", None)
    bad_obj.pop("response_time_ms", None)
    assert parser.process_line(json.dumps(bad_obj), source="KAFKA") is False

    parser.flush()

    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM metrics")
            metric_count = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM ingestion_errors")
            error_count = cur.fetchone()[0]
        assert metric_count == len(good)
        assert error_count >= 1
    finally:
        release_conn(conn)
