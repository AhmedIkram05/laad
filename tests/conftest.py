import os
import pytest
from dotenv import load_dotenv

load_dotenv()

os.environ["POSTGRES_HOST"] = os.getenv("TEST_POSTGRES_HOST", "localhost")
os.environ["POSTGRES_PORT"] = os.getenv("TEST_POSTGRES_PORT", "5433")
os.environ["POSTGRES_DB"] = os.getenv("TEST_POSTGRES_DB", "atm_platform_test")
os.environ["POSTGRES_USER"] = os.getenv("TEST_POSTGRES_USER", "atm_user")
os.environ["POSTGRES_PASSWORD"] = os.getenv("TEST_POSTGRES_PASSWORD", "your_password_here")

@pytest.fixture
def db_config():
    return {
        "host": os.environ["POSTGRES_HOST"],
        "port": int(os.environ["POSTGRES_PORT"]),
        "dbname": os.environ["POSTGRES_DB"],
        "user": os.environ["POSTGRES_USER"],
        "password": os.environ["POSTGRES_PASSWORD"],
    }