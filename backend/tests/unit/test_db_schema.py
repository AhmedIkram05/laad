from backend.src.database.connection import get_conn, release_conn
from backend.tests.helpers import reset_test_db


def _table_columns(cur, table_name: str):
    cur.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = %s
        ORDER BY ordinal_position
        """,
        (table_name,),
    )
    return [row[0] for row in cur.fetchall()]


def test_tables_exist():
    reset_test_db()

    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT tablename
                FROM pg_catalog.pg_tables
                WHERE schemaname = 'public'
                """
            )
            tables = {r[0] for r in cur.fetchall()}

        expected_tables = {
            "atms",
            "events",
            "metrics",
            "anomalies",
            "ingestion_errors",
            "users",
            "retention_config",
        }
        assert expected_tables.issubset(tables)
    finally:
        release_conn(conn)


def test_column_shape_and_view_presence():
    reset_test_db()

    conn = get_conn()
    try:
        with conn.cursor() as cur:
            events_cols = _table_columns(cur, "events")
            assert "transaction_id" in events_cols
            assert "correlation_id" in events_cols

            atms_cols = _table_columns(cur, "atms")
            assert "os_version" in atms_cols

            anomalies_cols = _table_columns(cur, "anomalies")
            assert "feedback_rating" in anomalies_cols
            assert "transaction_id" in anomalies_cols
            assert "recommended_action" in anomalies_cols
            assert "model_confidence_score" in anomalies_cols

            cur.execute("SELECT * FROM v_unified_analysis LIMIT 0")
            view_cols = [d[0] for d in cur.description]

        expected_view_cols = [
            "atm_id",
            "atm_status",
            "component",
            "error_code",
            "error_detail",
            "correlation_id",
        ]
        for col in expected_view_cols:
            assert col in view_cols
    finally:
        release_conn(conn)
