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

        seed_recommendations(cursor)
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

def seed_recommendations(cursor):
    """Seed the recommendation templates into the recommendations table."""
    # Recommendation templates from the project spec
    recommendations_data = [
        (
            'A1', 
            'Network Timeout Cascade', 
            json.dumps(['Check Core Banking network route', 'Failover to secondary switch'])
        ),
        (
            'A2', 
            'Cash Cassette Depletion -> Out of Service', 
            json.dumps(['Dispatch CIT for replenishment', 'Update ATM status to Out of Service'])
        ),
        (
            'A3', 
            'JVM Memory Leak -> OOM', 
            json.dumps(['Restart Java application service', 'Trigger heap dump for analysis'])
        ),
        (
            'A4', 
            'Container Restart Loop', 
            json.dumps(['Check container orchestrator logs', 'Rollback to previous container image'])
        ),
        (
            'A5', 
            'High Response Time Spike + Success Rate Drop', 
            json.dumps(['Investigate downstream API latency', 'Scale up processing nodes'])
        ),
        (
            'A6', 
            'OS Memory Pressure -> Application Timeout', 
            json.dumps(['Kill non-essential background processes', 'Schedule remote ATM reboot'])
        ),
        (
            'A7', 
            'Malformed / Out-of-Order Kafka Events', 
            json.dumps(['Validate message schema versions', 'Check producer clock synchronisation'])
        )
    ]
    
    logging.info("Seeding recommendation templates...")
    
    cursor.executemany('''
        INSERT OR IGNORE INTO recommendations (anomaly_type, root_cause, actions)
        VALUES (?, ?, ?)
    ''', recommendations_data)
    
    logging.info(f"Seeded {len(recommendations_data)} recommendation templates.")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    init_db()
