from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

import bcrypt

from backend.src.database.connection import get_conn, release_conn

logger = logging.getLogger(__name__)
THIS_DIR = Path(__file__).resolve().parent


def _read_schema(schema_path: str = "schema.sql") -> str:
    full_schema_path = THIS_DIR / schema_path
    with open(full_schema_path, "r", encoding="utf-8") as fh:
        return fh.read()


def seed_atms(conn) -> None:
    atms = [(f"ATM-GB-{str(i).zfill(4)}", "linux-5.19", f"LOC-{str(i).zfill(4)}") for i in range(1, 11)]
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO atms (atm_id, os_version, location_code) VALUES (%s, %s, %s) ON CONFLICT (atm_id) DO NOTHING",
            atms,
        )


def seed_default_admin(conn) -> None:
    password_hash = bcrypt.hashpw(b"admin", bcrypt.gensalt()).decode()
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO users (username, password_hash, role, created_at)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (username) DO NOTHING
            """,
            ("admin", password_hash, "admin", datetime.now(timezone.utc)),
        )


def seed_retention_config(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO retention_config (id, retention_days, updated_at)
            VALUES (1, %s, %s)
            ON CONFLICT (id) DO UPDATE
            SET retention_days = EXCLUDED.retention_days,
                updated_at = EXCLUDED.updated_at
            """,
            (7, datetime.now(timezone.utc)),
        )


def init_db(schema_path: str = "schema.sql", db_path=None, force: bool = False) -> bool:
    """Initialise PostgreSQL schema and seed default data.

    `db_path` is ignored and kept only for backwards compatibility with
    existing call sites/tests from the SQLite era.
    """
    if db_path is not None:
        logger.info("init_db(db_path=...) is deprecated under PostgreSQL and is ignored")

    schema_sql = _read_schema(schema_path)

    conn = get_conn()
    try:
        if force:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    DROP VIEW IF EXISTS v_unified_analysis;
                    DROP VIEW IF EXISTS v_metrics_flat;
                    DROP VIEW IF EXISTS v_events_flat;
                    DROP TABLE IF EXISTS anomalies;
                    DROP TABLE IF EXISTS ingestion_errors;
                    DROP TABLE IF EXISTS metrics;
                    DROP TABLE IF EXISTS events;
                    DROP TABLE IF EXISTS users;
                    DROP TABLE IF EXISTS retention_config;
                    DROP TABLE IF EXISTS atms;
                    """
                )
            conn.commit()

        with conn.cursor() as cur:
            cur.execute(schema_sql)
        with conn.cursor() as cur:
            cur.execute("""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'metrics' AND column_name = 'correlation_id'
                    ) THEN
                        ALTER TABLE metrics ADD COLUMN correlation_id TEXT;
                    END IF;
                END $$;
            """)
        conn.commit()
        seed_atms(conn)
        seed_default_admin(conn)
        seed_retention_config(conn)
        conn.commit()
        logger.info("Database initialised successfully")
        return True
    except Exception:
        conn.rollback()
        logger.exception("Failed to initialise database")
        raise
    finally:
        release_conn(conn)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    init_db()
