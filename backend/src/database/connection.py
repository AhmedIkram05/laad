import sqlite3
from pathlib import Path

# Default database path — match generator output location
# Uses the project's `custom_synthetic_data_sources/database/database.db`
OUTPUT_DIR = Path("custom_synthetic_data_sources")
DB_PATH = str(OUTPUT_DIR.joinpath("database", "database.db"))

def get_db(db_path: str | None = None):
    """Return a configured SQLite connection.

    This applies recommended PRAGMA settings for better concurrent writes
    (WAL, busy timeout, sensible synchronous mode) and enables foreign keys.
    """
    # Ensure parent directory exists so sqlite can create the DB file
    p = Path(db_path or DB_PATH)
    parent = p.parent
    try:
        parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        # If we cannot create the directory, let sqlite raise a clear error
        pass
    conn = sqlite3.connect(str(p), timeout=5.0)
    conn.row_factory = sqlite3.Row
    # Apply robust runtime settings for concurrency and performance
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA temp_store = MEMORY")
    conn.execute("PRAGMA cache_size = -64000")
    return conn
