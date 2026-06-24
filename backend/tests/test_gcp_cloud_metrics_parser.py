from backend.src.database.connection import get_conn, release_conn
from backend.src.ingestion.parsers.gcp_cloud_metrics import GcpCloudMetricsParser
from backend.tests.helpers import reset_test_db, sample_path


def test_gcp_good_and_bad_rows():
    reset_test_db()
    parser = GcpCloudMetricsParser(batch_size=10)

    with open(sample_path("gcp_cloud_metrics.csv"), "r", encoding="utf-8") as f:
        lines = f.readlines()

    good = [lines[1].strip(), lines[3].strip()]
    for line in good:
        assert parser.process_line(line, source="CLOUD") is True

    bad = "2026-03-05T09:00:00.000Z,synth-banking-sim-001,gke_container,terminal-handler-pod-xxx,europe-west2-b,container/cpu/usage_time,,s{CPU},"
    assert parser.process_line(bad, source="CLOUD") is False

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
