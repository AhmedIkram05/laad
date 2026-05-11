import os
import pytest


os.environ["POSTGRES_HOST"] = os.getenv("TEST_POSTGRES_HOST", "localhost")
os.environ["POSTGRES_PORT"] = os.getenv("TEST_POSTGRES_PORT", "5433")
os.environ["POSTGRES_DB"] = os.getenv("TEST_POSTGRES_DB", "atm_platform_test")
os.environ["POSTGRES_USER"] = os.getenv("TEST_POSTGRES_USER", "atm_user")
os.environ["POSTGRES_PASSWORD"] = os.getenv("TEST_POSTGRES_PASSWORD", "your_password_here")

from backend.src.ingestion.custom_data_generator import generate_dataset


@pytest.fixture(scope='session', autouse=True)
def seeded_dataset(tmp_path_factory):
    """Generate a small deterministic dataset for tests and expose its path.

    Use `tmp_path_factory` because this fixture is session-scoped.
    """
    # Always generate a deterministic, small dataset for tests and expose its path.
    out_path = tmp_path_factory.mktemp('synthetic')
    out = str(out_path)
    os.makedirs(out, exist_ok=True)
    generate_dataset(output=out, hours=1, seed=42)
    os.environ['TEST_DATA_DIR'] = out
    return out


@pytest.fixture(scope="session", autouse=True)
def ensure_db_schema():
    """Ensure the Postgres schema exists for tests.

    Requires a Postgres instance reachable via environment variables
    (POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD).
    """
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
