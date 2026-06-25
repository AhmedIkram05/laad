"""Repository-level pytest configuration.

Ensure the repository root is on sys.path before tests import modules so
package imports like `from backend...` resolve regardless of CWD.
"""

from __future__ import annotations

import sys
import pytest
import os
from pathlib import Path


def pytest_configure(config) -> None:
    """Register custom markers to suppress PytestUnknownMarkWarning."""
    config.addinivalue_line(
        "markers", "kafka: tests that require a running Kafka broker"
    )
    config.addinivalue_line(
        "markers", "rag: tests that require the RAG pipeline (ChromaDB + LLM)"
    )
    config.addinivalue_line(
        "markers", "chroma: tests that require a running ChromaDB instance"
    )


def pytest_sessionstart(session) -> None:
    repo_root = Path(__file__).resolve().parent
    repo_root_str = str(repo_root)
    if repo_root_str not in sys.path:
        sys.path.insert(0, repo_root_str)


@pytest.fixture(scope="session", autouse=True)
def setup_test_data_dir():
    """Ensure TEST_DATA_DIR is set for legacy parser tests using existing synthetic data."""
    os.environ["TEST_DATA_DIR"] = os.path.abspath(
        "backend/custom_synthetic_data_sources"
    )
