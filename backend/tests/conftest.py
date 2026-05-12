import os
import pytest
from unittest.mock import patch

test_host = os.getenv("TEST_POSTGRES_HOST")
if test_host is None:
    in_docker = os.path.exists("/.dockerenv")
    test_host = "host.docker.internal" if in_docker else "localhost"
os.environ["POSTGRES_HOST"] = test_host
os.environ["POSTGRES_PORT"] = os.getenv("TEST_POSTGRES_PORT", "5433")
os.environ["POSTGRES_DB"] = os.getenv("TEST_POSTGRES_DB", "atm_platform_test")
os.environ["POSTGRES_USER"] = os.getenv("TEST_POSTGRES_USER", "atm_user")
os.environ["POSTGRES_PASSWORD"] = os.getenv("TEST_POSTGRES_PASSWORD", "your_password_here")

@pytest.fixture(scope="session", autouse=True)
def setup_database():
    """Seed baseline data and clean up DB between tests."""
    from backend.src.database import config
    
    config.DB_CONFIG["host"] = os.environ["POSTGRES_HOST"]
    config.DB_CONFIG["port"] = int(os.environ["POSTGRES_PORT"])
    config.DB_CONFIG["dbname"] = os.environ["POSTGRES_DB"]
    config.DB_CONFIG["user"] = os.environ["POSTGRES_USER"]
    config.DB_CONFIG["password"] = os.environ["POSTGRES_PASSWORD"]

    from backend.src.database.connection import get_cursor
    import bcrypt
    
    with get_cursor(commit=True) as cur:
        atms = [f"ATM-GB-{str(i).zfill(4)}" for i in range(1, 11)]
        cur.execute("TRUNCATE TABLE events, metrics, anomalies, ingestion_errors, users CASCADE")
        cur.execute("DELETE FROM atms")
        for atm in atms:
            cur.execute("INSERT INTO atms (atm_id) VALUES (%s)", (atm,))
        
        admin_hash = bcrypt.hashpw(b'admin', bcrypt.gensalt()).decode()
        cur.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (%s, %s, %s)",
            ("admin", admin_hash, "admin")
        )

@pytest.fixture
def db_cleanup():
    """Truncates all data tables before each test."""
    from backend.src.database.connection import get_cursor
    with get_cursor(commit=True) as cur:
        cur.execute("TRUNCATE TABLE events, metrics, anomalies, ingestion_errors CASCADE")

@pytest.fixture(scope="session", autouse=True)
def refresh_schema():
    """Re-apply schema after each test module to pick up schema changes."""
    pass

@pytest.fixture(scope="module", autouse=True)
def ensure_db_schema():
    """Re-apply schema before each test module to pick up schema changes."""
    from backend.src.database.connection import get_conn, release_conn
    import backend.src.database.init_db as init_db
    conn = get_conn()
    try:
        init_db.init_db()
    finally:
        release_conn(conn)

@pytest.fixture(autouse=True)
def override_db_dependency(monkeypatch):
    """Override the FastAPI dependency `get_db_connection` to yield pooled conn."""
    import backend.src.auth.auth_router as auth_router
    from backend.src.database.connection import get_conn, release_conn
    def get_db_connection_override():
        conn = get_conn()
        try:
            yield conn
        finally:
            release_conn(conn)
    monkeypatch.setattr(auth_router, "get_db_connection", get_db_connection_override)