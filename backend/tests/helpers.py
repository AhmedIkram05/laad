import os

from backend.src.database.connection import get_conn, release_conn


def sample_path(filename: str) -> str:
    base = os.environ.get('TEST_DATA_DIR')
    if not base:
        raise RuntimeError('TEST_DATA_DIR is not set; tests expect generated dataset to be available via the seeded fixture')
    return os.path.join(base, filename)


def clear_core_tables() -> None:
    """Best-effort truncation for core app tables used in tests."""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                TRUNCATE TABLE
                    anomalies,
                    metrics,
                    events,
                    ingestion_errors,
                    users,
                    atms,
                    retention_config
                RESTART IDENTITY CASCADE
                """
            )
        conn.commit()
    finally:
        release_conn(conn)


def seed_test_defaults() -> None:
    """Re-seed minimal required rows after a truncate."""
    from backend.src.database.init_db import seed_atms, seed_default_admin, seed_retention_config

    conn = get_conn()
    try:
        seed_atms(conn)
        seed_default_admin(conn)
        seed_retention_config(conn)
        conn.commit()
    finally:
        release_conn(conn)


def reset_test_db() -> None:
    clear_core_tables()
    seed_test_defaults()
