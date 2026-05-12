"""Unit tests for live generator emitters."""
from __future__ import annotations
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone
from backend.generator.emitters import (
    emit_atm_app_events, 
    emit_hardware_events, 
    emit_terminal_handler_events,
    emit_kafka_metrics,
    emit_prometheus_metrics,
    emit_windows_os_metrics,
    emit_gcp_metrics
)

def test_atm_app_emitter():
    mock_cur = MagicMock()
    t = datetime.now(timezone.utc)
    emit_atm_app_events(mock_cur, t)
    assert mock_cur.execute.called

def test_hardware_emitter():
    with patch('backend.generator.emitters.random.random', return_value=0.0):
        mock_cur = MagicMock()
        t = datetime.now(timezone.utc)
        emit_hardware_events(mock_cur, t)
        assert mock_cur.execute.called

def test_terminal_handler_emitter():
    with patch('backend.generator.emitters.random.random', return_value=0.0):
        mock_cur = MagicMock()
        t = datetime.now(timezone.utc)
        emit_terminal_handler_events(mock_cur, t)
        assert mock_cur.execute.called

def test_kafka_metrics_emitter():
    mock_cur = MagicMock()
    t = datetime.now(timezone.utc)
    emit_kafka_metrics(mock_cur, t)
    assert mock_cur.execute.called

def test_prometheus_metrics_emitter():
    mock_cur = MagicMock()
    t = datetime.now(timezone.utc)
    emit_prometheus_metrics(mock_cur, t)
    assert mock_cur.execute.called

def test_windows_os_metrics_emitter():
    mock_cur = MagicMock()
    t = datetime.now(timezone.utc)
    emit_windows_os_metrics(mock_cur, t)
    assert mock_cur.execute.called

def test_gcp_metrics_emitter():
    mock_cur = MagicMock()
    t = datetime.now(timezone.utc)
    emit_gcp_metrics(mock_cur, t)
    assert mock_cur.execute.called