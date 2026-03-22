import sqlite3
import os

# Resolve absolute path to database.db
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'database.db')

def get_db(db_path: str | None = None):
    """Return a configured SQLite connection.

    This applies recommended PRAGMA settings for better concurrent writes
    (WAL, busy timeout, sensible synchronous mode) and enables foreign keys.
    """
    path = db_path or DB_PATH
    conn = sqlite3.connect(path, timeout=5.0)
    conn.row_factory = sqlite3.Row
    # Apply robust runtime settings for concurrency and performance
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA temp_store = MEMORY")
    conn.execute("PRAGMA cache_size = -64000")
    return conn
