import os
import sys
import time

import psycopg2
import pytest

test_host = os.getenv("TEST_POSTGRES_HOST")
if test_host is None:
    in_docker = os.path.exists("/.dockerenv")
    test_host = "host.docker.internal" if in_docker else "localhost"
os.environ["POSTGRES_HOST"] = test_host
os.environ["POSTGRES_PORT"] = os.getenv("TEST_POSTGRES_PORT", "5433")
os.environ["POSTGRES_DB"] = os.getenv("TEST_POSTGRES_DB", "atm_platform_test")
os.environ["POSTGRES_USER"] = os.getenv("TEST_POSTGRES_USER", "atm_user")
os.environ["POSTGRES_PASSWORD"] = os.getenv(
    "TEST_POSTGRES_PASSWORD", "your_password_here"
)

# Ensure TEST_DATA_DIR is set for legacy parser tests using existing synthetic data.
# The root conftest.py does this on host but isn't available inside the Docker image.
_test_data_dir = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "custom_synthetic_data_sources")
)
if os.path.isdir(_test_data_dir):
    os.environ.setdefault("TEST_DATA_DIR", _test_data_dir)

_kafka_mock = None


@pytest.fixture(scope="session", autouse=True)
def mock_kafka_module():
    global _kafka_mock
    from unittest.mock import MagicMock

    _kafka_mock = MagicMock()
    original_modules = {}
    for mod_name in ["kafka", "kafka.errors", "kafka.producer", "kafka.consumer"]:
        if mod_name in sys.modules:
            original_modules[mod_name] = sys.modules.pop(mod_name)
    sys.modules["kafka"] = _kafka_mock
    sys.modules["kafka.errors"] = _kafka_mock.errors
    sys.modules["kafka.producer"] = _kafka_mock.producer
    sys.modules["kafka.consumer"] = _kafka_mock.consumer
    yield
    for mod_name in list(sys.modules.keys()):
        if mod_name.startswith("kafka"):
            sys.modules.pop(mod_name, None)
    sys.modules.update(original_modules)


@pytest.fixture(scope="session", autouse=True)
def setup_database():
    """Seed ATM baseline data once per session. Run once at session start."""
    from backend.src.database import config

    config.DB_CONFIG["host"] = os.environ["POSTGRES_HOST"]
    config.DB_CONFIG["port"] = int(os.environ["POSTGRES_PORT"])
    config.DB_CONFIG["dbname"] = os.environ["POSTGRES_DB"]
    config.DB_CONFIG["user"] = os.environ["POSTGRES_USER"]
    config.DB_CONFIG["password"] = os.environ["POSTGRES_PASSWORD"]

    from backend.src.database.connection import get_cursor, get_conn, release_conn
    import bcrypt

    # Deadlock-retry TRUNCATE to handle concurrent TestClient sessions
    DEADLOCK_RETRIES = 3
    DEADLOCK_BACKOFF = 0.5
    for attempt in range(DEADLOCK_RETRIES):
        trunc_conn = get_conn()
        try:
            with trunc_conn.cursor() as cur:
                cur.execute(
                    "TRUNCATE TABLE events, metrics, anomalies, ingestion_errors, users CASCADE"
                )
            trunc_conn.commit()
            break
        except psycopg2.errors.DeadlockDetected:
            trunc_conn.rollback()
            if attempt < DEADLOCK_RETRIES - 1:
                time.sleep(DEADLOCK_BACKOFF * (2**attempt))
                continue
            raise
        finally:
            release_conn(trunc_conn)

    with get_cursor(commit=True) as cur:
        admin_hash = bcrypt.hashpw(b"admin", bcrypt.gensalt()).decode()
        cur.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (%s, %s, %s) "
            "ON CONFLICT (username) DO UPDATE SET password_hash = EXCLUDED.password_hash, role = EXCLUDED.role",
            ("admin", admin_hash, "admin"),
        )


@pytest.fixture
def db_cleanup():
    """Truncates all data tables before each test."""
    from backend.src.database.connection import get_cursor

    with get_cursor(commit=True) as cur:
        cur.execute(
            "TRUNCATE TABLE events, metrics, anomalies, ingestion_errors CASCADE"
        )


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
