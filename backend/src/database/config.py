"""PostgreSQL connection configuration loaded from environment variables.

This module centralises DB connection settings for the project.
"""

from __future__ import annotations

import os
from dotenv import load_dotenv

load_dotenv()

DB_CONFIG = {
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": int(os.getenv("POSTGRES_PORT", "5432")),
    "dbname": os.getenv("POSTGRES_DB", "atm_platform"),
    "user": os.getenv("POSTGRES_USER", "atm_user"),
    "password": os.getenv("POSTGRES_PASSWORD", ""),
}
