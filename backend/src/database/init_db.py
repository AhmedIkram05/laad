import sqlite3
import os
import json
import logging
from datetime import datetime, timezone

def init_db(db_path=None, schema_path='schema.sql'):
    """Initialise the database with the defined schema.

    If `db_path` is None, use the central `DB_PATH` from
    `backend.database.connection` so the generator and ingestion
    components stay in sync.
    """
    # Resolve database path: prefer explicit, then env/central default
    if db_path is None:
        try:
            from backend.src.database.connection import DB_PATH as DEFAULT_DB_PATH
            full_db_path = DEFAULT_DB_PATH
        except Exception:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            full_db_path = os.path.join(base_dir, 'database.db')
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        full_db_path = os.path.join(base_dir, db_path)
    full_schema_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), schema_path)
    
    logging.info(f"Initialising database at {full_db_path}")
    
    # Read the schema
    try:
        with open(full_schema_path, 'r') as f:
            schema_sql = f.read()
    except FileNotFoundError:
        logging.error(f"Schema file not found at {full_schema_path}")
        return False

    # Connect to the database and execute schema
    try:
        # Remove existing database file to ensure a clean run (avoid mixing
        # data from previous runs which can create spurious cross-day anomalies).
        if os.path.exists(full_db_path):
            try:
                os.remove(full_db_path)
                logging.info(f"Removed existing database file: {full_db_path}")
            except Exception:
                logging.exception("Failed to remove existing database file; continuing")
        # Use the centralised connection bootstrap so PRAGMAs are applied
        from backend.src.database.connection import get_db

        conn = get_db(full_db_path)
        cursor = conn.cursor()

        # Execute the schema
        cursor.executescript(schema_sql)

        conn.commit()
        logging.info("Schema applied successfully.")
        seed_atms(cursor)
        # Seed a default admin account if no users exist yet
        seed_default_admin(cursor)
        # Seed retention config single row (id=1) with ISO8601 UTC timestamp
        seed_retention_config(cursor)
        conn.commit()

    except sqlite3.Error as e:
        logging.error(f"Database error: {e}")
        return False
    finally:
        try:
            if conn:
                conn.close()
        except Exception:
            pass
            
    return True

def seed_atms(cursor):
    """Seed the reference table of ATMs tracked by the system.
    
    Derives all ATM reference data directly from the generator constants so
    the database always reflects the active synthetic fleet. No hardcoded
    ATM IDs should exist here.
    """
    try:
        from backend.src.ingestion.custom_data_generator import ATMS, OS_VERSION, ATM_LOCATIONS
    except ImportError:
        # Fallback if generator is temporarily unavailable — must match generator fleet
        ATMS = ['ATM-GB-0001', 'ATM-GB-0002', 'ATM-GB-0003', 'ATM-GB-0004']
        OS_VERSION = 'Windows-Server-2019'
        ATM_LOCATIONS = {
            'ATM-GB-0001': 'LOC-001',
            'ATM-GB-0002': 'LOC-002',
            'ATM-GB-0003': 'LOC-003',
            'ATM-GB-0004': 'LOC-004',
        }

    # Seed exactly the ATMs defined in the generator — nothing more, nothing less
    atms_data = [(atm_id, OS_VERSION, ATM_LOCATIONS.get(atm_id, 'LOC-UNKNOWN')) for atm_id in ATMS]

    logging.info("Seeding ATM reference data...")
    cursor.executemany('''
        INSERT OR IGNORE INTO atms (atm_id, os_version, location_code)
        VALUES (?, ?, ?)
    ''', atms_data)
    logging.info(f"Seeded {len(atms_data)} ATMs.")


def seed_default_admin(cursor):
    """Seeds a default admin account on first run only.
    Username: admin | Password: admin
    The admin should change this password after first login.
    """
    try:
        import bcrypt
    except Exception:
        logging.error("bcrypt is required to seed the default admin account")
        return

    cursor.execute("SELECT COUNT(*) FROM users")
    row = cursor.fetchone()
    if row and row[0] > 0:
        return  # users already exist, never overwrite

    passwordHash = bcrypt.hashpw(b"admin", bcrypt.gensalt()).decode()
    cursor.execute(
        """INSERT INTO users (username, password_hash, role, created_at)
           VALUES (?, ?, 'admin', datetime('now'))""",
        ("admin", passwordHash)
    )
    logging.info("Seeded default admin (username: admin, password: admin)")


def seed_retention_config(cursor):
    """Ensure a single-row retention_config exists.

    Uses an ISO8601 UTC timestamp for `updated_at` to match application usage.
    """
    cursor.execute("SELECT retention_days FROM retention_config WHERE id = 1")
    row = cursor.fetchone()
    if row:
        return

    now_iso = datetime.now(timezone.utc).isoformat()
    cursor.execute(
        "INSERT INTO retention_config (id, retention_days, updated_at) VALUES (1, ?, ?)",
        (7, now_iso)
    )
    logging.info("Seeded retention_config (id=1, retention_days=7)")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    init_db()
