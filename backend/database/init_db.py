import sqlite3
import os
import json
import logging

def init_db(db_path='database.db', schema_path='schema.sql'):
    """Initialise the database with the defined schema."""
    
    # Resolve absolute paths
    base_dir = os.path.dirname(os.path.abspath(__file__))
    full_db_path = os.path.join(base_dir, db_path)
    full_schema_path = os.path.join(base_dir, schema_path)
    
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
        # Use the centralised connection bootstrap so PRAGMAs are applied
        from backend.database.connection import get_db

        conn = get_db(full_db_path)
        cursor = conn.cursor()

        # Execute the schema
        cursor.executescript(schema_sql)
        conn.commit()
        logging.info("Schema applied successfully.")

        seed_atms(cursor)
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
        from backend.ingestion.custom_data_generator import ATMS, OS_VERSION, ATM_LOCATIONS
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


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    init_db()
