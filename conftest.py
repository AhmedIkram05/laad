"""Repository-level pytest configuration.

Ensure the repository root is on sys.path before tests import modules so
package imports like `from backend...` resolve regardless of CWD.
"""
from __future__ import annotations

import sys
from pathlib import Path


def pytest_sessionstart(session) -> None:
    repo_root = Path(__file__).resolve().parent
    repo_root_str = str(repo_root)
    if repo_root_str not in sys.path:
        sys.path.insert(0, repo_root_str)
