"""Unit tests for anomaly injectors."""
from __future__ import annotations
import pytest
from unittest.mock import MagicMock
from datetime import datetime, timezone
import psycopg2.extras
from backend.generator.anomaly_injectors import (
    inject_a1, inject_a2, inject_a3, inject_a4, inject_a5, inject_a6, inject_a7
)

def test_inject_a1():
    mock_cur = MagicMock()
    t = datetime.now(timezone.utc)
    inject_a1(mock_cur, t)
    assert mock_cur.execute.called
    found_tag = False
    for call in mock_cur.execute.call_args_list:
        args_tuple = call[0][1]
        payload = args_tuple[8]
        payload_dict = payload.adapted if hasattr(payload, 'adapted') else None
        if payload_dict and "_anomaly_tag" in payload_dict:
            found_tag = True
    assert found_tag, "No _anomaly_tag found in inject_a1 payloads"

def test_inject_a2():
    mock_cur = MagicMock()
    t = datetime.now(timezone.utc)
    inject_a2(mock_cur, t)
    assert mock_cur.execute.called

def test_inject_a3():
    mock_cur = MagicMock()
    t = datetime.now(timezone.utc)
    inject_a3(mock_cur, t)
    assert mock_cur.execute.called

def test_inject_a4():
    mock_cur = MagicMock()
    t = datetime.now(timezone.utc)
    inject_a4(mock_cur, t)
    assert mock_cur.execute.called

def test_inject_a5():
    mock_cur = MagicMock()
    t = datetime.now(timezone.utc)
    inject_a5(mock_cur, t)
    assert mock_cur.execute.called

def test_inject_a6():
    mock_cur = MagicMock()
    t = datetime.now(timezone.utc)
    inject_a6(mock_cur, t)
    assert mock_cur.execute.called

def test_inject_a7():
    mock_cur = MagicMock()
    t = datetime.now(timezone.utc)
    inject_a7(mock_cur, t)
    assert mock_cur.execute.called