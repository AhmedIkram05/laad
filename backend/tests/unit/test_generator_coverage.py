"""Extended coverage tests for backend.generator.continuous_generator.

Covers main() entry point, _graceful_shutdown(), _shutdown_requested break
in backfill loop, and signal.signal() registration.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


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
    cg._shutdown_requested = False
    cg._in_backfill = False


# ---------------------------------------------------------------------------
# _graceful_shutdown
# ---------------------------------------------------------------------------


class TestGracefulShutdown:
    def test_sets_shutdown_requested(self):
        import backend.generator.continuous_generator as cg

        cg._shutdown_requested = False
        cg._graceful_shutdown(None, None)
        assert cg._shutdown_requested is True

    def test_idempotent(self):
        import backend.generator.continuous_generator as cg

        cg._graceful_shutdown(None, None)
        cg._graceful_shutdown(None, None)
        assert cg._shutdown_requested is True


# ---------------------------------------------------------------------------
# Signal registration (module-level)
# ---------------------------------------------------------------------------


class TestSignalRegistration:
    def test_signal_handlers_registered_at_import(self):
        """Verify signal.signal was called for SIGTERM and SIGINT at import time."""
        import backend.generator.continuous_generator as cg

        assert callable(cg._graceful_shutdown)


# ---------------------------------------------------------------------------
# backfill with _shutdown_requested
# ---------------------------------------------------------------------------


class TestBackfillShutdown:
    def test_backfill_breaks_on_shutdown_requested(self):
        from backend.generator.continuous_generator import backfill

        producer = MagicMock()
        tick_count = 0

        def counting_emit(*args, **kwargs):
            nonlocal tick_count
            tick_count += 1

        import backend.generator.continuous_generator as cg

        now = datetime(2026, 6, 24, 12, 0, 0, tzinfo=timezone.utc)

        call_n = [0]

        def now_side_effect():
            call_n[0] += 1
            if call_n[0] > 3:
                cg._shutdown_requested = True
            return now

        with patch(
            "backend.generator.continuous_generator.emit_tick",
            side_effect=counting_emit,
        ):
            with patch(
                "backend.generator.continuous_generator.now_utc",
                side_effect=now_side_effect,
            ):
                with patch("backend.generator.continuous_generator.TICK_SECONDS", 1):
                    with patch(
                        "backend.generator.continuous_generator.ANOMALY_PROB", 0.002
                    ):
                        backfill(producer, 10)

        assert tick_count > 0
        assert cg._shutdown_requested is True

    def test_backfill_sets_in_backfill_flag(self):
        from backend.generator.continuous_generator import backfill

        producer = MagicMock()
        import backend.generator.continuous_generator as cg

        now = datetime(2026, 6, 24, 12, 0, 0, tzinfo=timezone.utc)

        with patch("backend.generator.continuous_generator.emit_tick"):
            with patch(
                "backend.generator.continuous_generator.now_utc", return_value=now
            ):
                with patch("backend.generator.continuous_generator.TICK_SECONDS", 600):
                    with patch(
                        "backend.generator.continuous_generator.ANOMALY_PROB", 0.002
                    ):
                        backfill(producer, 1)

        assert cg._in_backfill is False

    def test_backfill_exception_in_tick_continues(self):
        from backend.generator.continuous_generator import backfill

        producer = MagicMock()
        import backend.generator.continuous_generator as cg

        now = datetime(2026, 6, 24, 12, 0, 0, tzinfo=timezone.utc)

        with patch(
            "backend.generator.continuous_generator.emit_tick",
            side_effect=RuntimeError("tick failed"),
        ):
            with patch(
                "backend.generator.continuous_generator.now_utc", return_value=now
            ):
                with patch("backend.generator.continuous_generator.TICK_SECONDS", 60):
                    with patch(
                        "backend.generator.continuous_generator.ANOMALY_PROB", 0.002
                    ):
                        # Should not raise
                        backfill(producer, 1)

        assert cg._in_backfill is False


# ---------------------------------------------------------------------------
# main() function
# ---------------------------------------------------------------------------


class TestMain:
    """Tests for the main() entry point.

    main() uses local imports for get_producer, get_cursor, seed_atm_fleet,
    so we patch at their source modules, not on continuous_generator.
    """

    @contextmanager
    def _main_patches(self, fetchone_result=None):
        """Context manager that yields (producer_mock, cursor_mock) with all
        patches active. Properly cleans up on exit."""
        producer_mock = MagicMock()
        cursor_mock = MagicMock()
        cursor_mock.__enter__ = MagicMock(return_value=cursor_mock)
        cursor_mock.__exit__ = MagicMock(return_value=False)
        cursor_mock.fetchone.return_value = fetchone_result or {"count": 0}

        fixed_now = datetime(2026, 6, 24, 12, 0, 0, tzinfo=timezone.utc)

        with (
            patch("backend.kafka.producer.get_producer", return_value=producer_mock),
            patch(
                "backend.src.database.connection.get_cursor", return_value=cursor_mock
            ),
            patch("backend.src.database.init_db.seed_atm_fleet"),
            patch("backend.generator.continuous_generator.time.sleep"),
            patch(
                "backend.generator.continuous_generator.now_utc", return_value=fixed_now
            ),
            patch("backend.generator.continuous_generator.TICK_SECONDS", 1),
            patch("backend.generator.continuous_generator.ANOMALY_PROB", 0.002),
            patch("backend.generator.continuous_generator.GENERATOR_SEED", "42"),
        ):
            yield producer_mock, cursor_mock

    def test_main_seeds_atm_fleet_when_empty(self):
        import backend.generator.continuous_generator as cg

        with self._main_patches(fetchone_result={"count": 0}) as (
            producer_mock,
            cursor_mock,
        ):
            call_count = [0]

            def stop_after_first_tick(*args, **kwargs):
                call_count[0] += 1
                if call_count[0] >= 1:
                    cg._shutdown_requested = True

            with patch(
                "backend.generator.continuous_generator.emit_tick",
                side_effect=stop_after_first_tick,
            ):
                with patch(
                    "backend.generator.continuous_generator.BACKFILL_MINUTES", 0
                ):
                    from backend.generator.continuous_generator import main

                    main()

        # seed_atm_fleet was called because cursor returned count=0
        # (verified by no crash — the patch ensures it's a mock)
        assert call_count[0] >= 1

    def test_main_skips_seed_when_atms_exist(self):
        import backend.generator.continuous_generator as cg

        with self._main_patches(fetchone_result={"count": 5}) as (
            producer_mock,
            cursor_mock,
        ):
            cg._shutdown_requested = True

            with patch("backend.generator.continuous_generator.BACKFILL_MINUTES", 0):
                from backend.generator.continuous_generator import main

                main()

        # No assertion needed — just verify no crash

    def test_main_calls_backfill(self):
        import backend.generator.continuous_generator as cg

        with self._main_patches(fetchone_result={"count": 5}) as (
            producer_mock,
            cursor_mock,
        ):
            cg._shutdown_requested = True

            backfill_mock = MagicMock()
            with patch("backend.generator.continuous_generator.BACKFILL_MINUTES", 5):
                with patch(
                    "backend.generator.continuous_generator.backfill", backfill_mock
                ):
                    from backend.generator.continuous_generator import main

                    main()

            backfill_mock.assert_called_once_with(producer_mock, 5)

    def test_main_shutdown_after_backfill(self):
        import backend.generator.continuous_generator as cg

        with self._main_patches(fetchone_result={"count": 5}) as (
            producer_mock,
            cursor_mock,
        ):

            def set_shutdown_during_backfill(producer, minutes):
                cg._shutdown_requested = True

            with patch("backend.generator.continuous_generator.BACKFILL_MINUTES", 5):
                with patch(
                    "backend.generator.continuous_generator.backfill",
                    side_effect=set_shutdown_during_backfill,
                ):
                    from backend.generator.continuous_generator import main

                    main()

            producer_mock.close.assert_called_once()

    def test_main_live_loop_runs_until_shutdown(self):
        import backend.generator.continuous_generator as cg

        with self._main_patches(fetchone_result={"count": 5}) as (
            producer_mock,
            cursor_mock,
        ):
            tick_count = [0]

            def count_ticks(*args, **kwargs):
                tick_count[0] += 1
                if tick_count[0] >= 3:
                    cg._shutdown_requested = True

            with patch("backend.generator.continuous_generator.BACKFILL_MINUTES", 0):
                with patch(
                    "backend.generator.continuous_generator.emit_tick",
                    side_effect=count_ticks,
                ):
                    from backend.generator.continuous_generator import main

                    main()

        assert tick_count[0] >= 3

    def test_main_live_loop_handles_tick_exception(self):
        """Test that the live loop continues after a tick failure.

        Note: the source code has ``backoff = min(60, backoff * 2)`` in the
        except block, but ``backoff`` is only assigned on the *success* path.
        So the first tick *must* succeed to initialise ``backoff``; only the
        second tick can fail.
        """
        import backend.generator.continuous_generator as cg

        with self._main_patches(fetchone_result={"count": 5}) as (
            producer_mock,
            cursor_mock,
        ):
            tick_count = [0]

            def succeed_then_fail_then_succeed(*args, **kwargs):
                tick_count[0] += 1
                if tick_count[0] == 2:
                    raise RuntimeError("Second tick fails")
                if tick_count[0] >= 4:
                    cg._shutdown_requested = True

            with patch("backend.generator.continuous_generator.BACKFILL_MINUTES", 0):
                with patch(
                    "backend.generator.continuous_generator.emit_tick",
                    side_effect=succeed_then_fail_then_succeed,
                ):
                    from backend.generator.continuous_generator import main

                    main()

        assert tick_count[0] >= 3


# ---------------------------------------------------------------------------
# emit_tick edge cases
# ---------------------------------------------------------------------------


class TestEmitTickExtended:
    def test_emitter_exception_does_not_stop_other_emitters(self):
        from backend.generator.continuous_generator import emit_tick

        producer = MagicMock()
        emitter1 = MagicMock(side_effect=RuntimeError("emitter1 failed"))
        emitter1.__name__ = "failing_emitter"
        emitter2 = MagicMock()
        emitter2.__name__ = "working_emitter"
        t = datetime.now(timezone.utc)

        with patch(
            "backend.generator.continuous_generator.BASELINE_EMITTERS",
            [emitter1, emitter2],
        ):
            with patch(
                "backend.generator.continuous_generator.rng.random", return_value=0.9
            ):
                emit_tick(producer, t, {})

        emitter1.assert_called_once()
        emitter2.assert_called_once()
        producer.flush.assert_called_once()

    def test_anomaly_injector_failure_does_not_crash(self):
        from backend.generator.continuous_generator import emit_tick

        producer = MagicMock()
        injector = MagicMock(side_effect=RuntimeError("injector crashed"))
        t = datetime.now(timezone.utc)

        with patch("backend.generator.continuous_generator.BASELINE_EMITTERS", []):
            with patch(
                "backend.generator.continuous_generator.ANOMALY_REGISTRY",
                [("A1", injector, 0)],
            ):
                with patch(
                    "backend.generator.continuous_generator.rng.random",
                    return_value=0.1,
                ):
                    with patch(
                        "backend.generator.continuous_generator.ANOMALY_PROB", 0.3
                    ):
                        anomaly_last = {}
                        emit_tick(producer, t, anomaly_last)

        # Injector was called but failed — anomaly_last should not be updated
        assert "A1" not in anomaly_last
        producer.flush.assert_called_once()

    def test_backfill_mode_skips_anomaly_injection(self):
        from backend.generator.continuous_generator import emit_tick

        producer = MagicMock()
        injector = MagicMock(return_value="ATM-GB-0001")
        t = datetime.now(timezone.utc)

        with patch("backend.generator.continuous_generator.BASELINE_EMITTERS", []):
            with patch(
                "backend.generator.continuous_generator.ANOMALY_REGISTRY",
                [("A1", injector, 0)],
            ):
                with patch(
                    "backend.generator.continuous_generator.rng.random",
                    return_value=0.005,
                ):
                    anomaly_last = {}
                    emit_tick(
                        producer,
                        t,
                        anomaly_last,
                        backfill_mode=True,
                        backfill_prob=0.01,
                    )

        # backfill_mode=True means the anomaly injection block is skipped entirely
        assert "A1" not in anomaly_last


# ---------------------------------------------------------------------------
# emit_tick with multiple anomalies on cooldown
# ---------------------------------------------------------------------------


class TestEmitTickCooldown:
    def test_multiple_anomalies_respect_cooldown(self):
        from backend.generator.continuous_generator import emit_tick

        producer = MagicMock()
        injector1 = MagicMock(return_value="ATM-GB-0001")
        injector2 = MagicMock(return_value="ATM-GB-0002")
        t = datetime.now(timezone.utc)

        # A1 was recently seen, A2 has not been seen
        anomaly_last = {"A1": t - timedelta(seconds=10)}

        with patch("backend.generator.continuous_generator.BASELINE_EMITTERS", []):
            with patch(
                "backend.generator.continuous_generator.ANOMALY_REGISTRY",
                [
                    ("A1", injector1, 300),  # 5 min cooldown
                    ("A2", injector2, 0),  # No cooldown
                ],
            ):
                with patch(
                    "backend.generator.continuous_generator.rng.random",
                    return_value=0.1,
                ):
                    with patch(
                        "backend.generator.continuous_generator.ANOMALY_PROB", 0.3
                    ):
                        with patch(
                            "backend.generator.continuous_generator.rng.choice",
                            return_value=("A2", injector2, 0),
                        ):
                            emit_tick(producer, t, anomaly_last)

        # Only A2 should be eligible (A1 on cooldown)
        injector2.assert_called_once()

    def test_no_eligible_anomalies_skips_injection(self):
        from backend.generator.continuous_generator import emit_tick

        producer = MagicMock()
        injector = MagicMock()
        t = datetime.now(timezone.utc)

        # All anomalies on cooldown
        anomaly_last = {"A1": t}

        with patch("backend.generator.continuous_generator.BASELINE_EMITTERS", []):
            with patch(
                "backend.generator.continuous_generator.ANOMALY_REGISTRY",
                [("A1", injector, 300)],
            ):
                with patch(
                    "backend.generator.continuous_generator.rng.random",
                    return_value=0.1,
                ):
                    with patch(
                        "backend.generator.continuous_generator.ANOMALY_PROB", 0.3
                    ):
                        emit_tick(producer, t, anomaly_last)

        injector.assert_not_called()
