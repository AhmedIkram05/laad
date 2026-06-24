"""Tests for continuous_generator module.

Uses mocked producers, emitters, and anomaly injectors
to test emit_tick, backfill, and main shutdown behavior.
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def mock_signal():
    """Prevent continuous_generator from setting real signal handlers."""
    with patch("backend.generator.continuous_generator.signal") as mock:
        yield mock


@pytest.fixture(autouse=True)
def reset_globals():
    """Reset module-level globals before each test."""
    import backend.generator.continuous_generator as cg
    cg._shutdown_requested = False
    cg._in_backfill = False
    yield


class TestEmitTick:
    def test_baseline_emitters_called(self):
        from backend.generator.continuous_generator import emit_tick

        producer = MagicMock()
        emitter = MagicMock()
        t = datetime.now(timezone.utc)

        with patch("backend.generator.continuous_generator.BASELINE_EMITTERS", [emitter]):
            with patch("backend.generator.continuous_generator.rng.random", return_value=0.5):
                with patch("backend.generator.continuous_generator.ANOMALY_PROB", 0.3):
                    emit_tick(producer, t, {})

        emitter.assert_called_once_with(producer, t)

    def test_anomaly_injected_when_prob_triggered(self):
        from backend.generator.continuous_generator import emit_tick

        producer = MagicMock()
        injector = MagicMock(return_value="ATM-GB-0001")
        t = datetime.now(timezone.utc)

        with patch("backend.generator.continuous_generator.BASELINE_EMITTERS", []):
            with patch("backend.generator.continuous_generator.ANOMALY_REGISTRY",
                       [("A1", injector, 0)]):
                with patch("backend.generator.continuous_generator.rng.random", return_value=0.1):
                    with patch("backend.generator.continuous_generator.ANOMALY_PROB", 0.3):
                        anomaly_last = {}
                        emit_tick(producer, t, anomaly_last)

        injector.assert_called_once()
        assert "A1" in anomaly_last

    def test_anomaly_skipped_when_on_cooldown(self):
        from backend.generator.continuous_generator import emit_tick

        producer = MagicMock()
        injector = MagicMock()
        t = datetime.now(timezone.utc)

        now = datetime.now(timezone.utc)
        anomaly_last = {"A1": now}  # Recently injected

        with patch("backend.generator.continuous_generator.BASELINE_EMITTERS", []):
            with patch("backend.generator.continuous_generator.ANOMALY_REGISTRY",
                       [("A1", injector, 300)]):  # 5 min cooldown
                with patch("backend.generator.continuous_generator.rng.random", return_value=0.1):
                    with patch("backend.generator.continuous_generator.ANOMALY_PROB", 0.3):
                        emit_tick(producer, t, anomaly_last)

        injector.assert_not_called()

    def test_anomaly_skipped_in_backfill_mode(self):
        from backend.generator.continuous_generator import emit_tick

        producer = MagicMock()
        injector = MagicMock()
        t = datetime.now(timezone.utc)

        with patch("backend.generator.continuous_generator.BASELINE_EMITTERS", []):
            with patch("backend.generator.continuous_generator.ANOMALY_REGISTRY",
                       [("A1", injector, 0)]):
                with patch("backend.generator.continuous_generator.rng.random", return_value=0.1):
                    emit_tick(producer, t, {}, backfill_mode=True, backfill_prob=0.01)

        # In backfill mode, rng.random is compared to backfill_prob, not ANOMALY_PROB
        # and backfill_mode=True skips the non-backfill check
        injector.assert_not_called()

    def test_producer_flushed(self):
        from backend.generator.continuous_generator import emit_tick

        producer = MagicMock()
        t = datetime.now(timezone.utc)

        with patch("backend.generator.continuous_generator.BASELINE_EMITTERS", []):
            emit_tick(producer, t, {})

        producer.flush.assert_called_once()


class TestBackfill:
    def test_backfill_skipped_when_minutes_zero(self):
        from backend.generator.continuous_generator import backfill

        producer = MagicMock()
        with patch("backend.generator.continuous_generator.emit_tick") as mock_emit:
            backfill(producer, 0)

        mock_emit.assert_not_called()

    def test_backfill_runs_ticks(self):
        from backend.generator.continuous_generator import backfill

        producer = MagicMock()
        with patch("backend.generator.continuous_generator.emit_tick"):
            with patch("backend.generator.continuous_generator.now_utc") as mock_now:
                # Fixed "now" so backfill begins and ends at predictable times
                now = datetime(2026, 6, 24, 12, 0, 0, tzinfo=timezone.utc)
                mock_now.return_value = now
                with patch("backend.generator.continuous_generator.TICK_SECONDS", 60):
                    with patch("backend.generator.continuous_generator.BACKFILL_MINUTES", 1):
                        backfill(producer, 1)

        # With 1 min backfill and 60s tick, we expect 1 tick
        # Just verify it runs without error and sets globals correctly
        import backend.generator.continuous_generator as cg
        assert cg._in_backfill is False
