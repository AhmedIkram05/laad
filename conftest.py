"""Repository-level pytest configuration.
 
Ensure the repository root is on sys.path before tests import modules so
package imports like `from backend...` resolve regardless of CWD.
"""
from __future__ import annotations

import sys
import pytest
import os
from pathlib import Path
from backend.src.database.connection import get_cursor

def pytest_sessionstart(session) -> None:
    repo_root = Path(__file__).resolve().parent
    repo_root_str = str(repo_root)
    if repo_root_str not in sys.path:
        sys.path.insert(0, repo_root_str)

@pytest.fixture(scope="session", autouse=True)
def setup_test_data_dir():
    """Ensure TEST_DATA_DIR is set for legacy parser tests using existing synthetic data."""
    os.environ['TEST_DATA_DIR'] = os.path.abspath('backend/custom_synthetic_data_sources')