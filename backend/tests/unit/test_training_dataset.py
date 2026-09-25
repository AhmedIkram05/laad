"""Tests for backend.generator.training_dataset."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest


class TestGenerateBaseline:
    def test_generate_baseline_returns_rows(self):
        from backend.generator.training_dataset import generate_baseline
        import datetime

        t = datetime.datetime(2026, 3, 5, 9, 0, 0)
        import random

        rng = random.Random(42)
        from backend.generator.config import ATMS

        atm = ATMS[0]

        rows = generate_baseline(t, atm, rng)
        assert len(rows) > 0
        # Should have metrics and events
        types = {r.get("metric_name") or r.get("event_type") for r in rows}
        assert "jvm_memory_usage" in types or any("jvm" in str(r) for r in rows)


class TestAnomalyInjectors:
    @pytest.fixture
    def setup(self):
        import datetime
        import random
        from backend.generator.config import ATMS

        self.t = datetime.datetime(2026, 3, 5, 9, 0, 0)
        self.rng = random.Random(42)
        self.atm = ATMS[0]
        self.rows = []
        self.corr_id = "test-corr"

    def test_inject_a1(self, setup):
        from backend.generator.training_dataset import inject_a1

        rows = []
        inject_a1(rows, self.t, self.atm, self.corr_id)
        assert len(rows) == 4
        types = [r["event_type"] for r in rows if r.get("event_type")]
        assert "NETWORK_DISCONNECT" in types

    def test_inject_a2(self, setup):
        from backend.generator.training_dataset import inject_a2

        rows = []
        inject_a2(rows, self.t, self.atm, self.corr_id)
        assert len(rows) == 5
        types = [r["event_type"] for r in rows if r.get("event_type")]
        assert "CASSETTE_LOW" in types
        assert "CASSETTE_EMPTY" in types

    def test_inject_a3(self, setup):
        from backend.generator.training_dataset import inject_a3

        rows = []
        inject_a3(rows, self.t, self.atm, self.corr_id)
        assert len(rows) > 0
        # Should have JVM metrics
        metric_names = [r["metric_name"] for r in rows if r.get("metric_name")]
        assert any("jvm" in m.lower() for m in metric_names)

    def test_inject_a4(self, setup):
        from backend.generator.training_dataset import inject_a4

        rows = []
        inject_a4(rows, self.t, self.atm, self.corr_id)
        assert len(rows) > 0
        types = [r["event_type"] for r in rows if r.get("event_type")]
        assert "STARTUP" in types

    def test_inject_a5(self, setup):
        from backend.generator.training_dataset import inject_a5

        rows = []
        inject_a5(rows, self.t, self.atm, self.corr_id)
        assert len(rows) > 0
        # A5 creates Kafka METRIC events with response_time_ms in payload
        kafka_events = [
            r
            for r in rows
            if r.get("source") == "KAFKA" and r.get("event_type") == "METRIC"
        ]
        assert len(kafka_events) > 0
        payloads = [json.loads(r["raw_payload"]) for r in kafka_events]
        assert any("response_time_ms" in p for p in payloads)

    def test_inject_a6(self, setup):
        from backend.generator.training_dataset import inject_a6

        rows = []
        inject_a6(rows, self.t, self.atm, self.corr_id)
        assert len(rows) > 0
        metric_names = [r["metric_name"] for r in rows if r.get("metric_name")]
        assert any("memory" in m for m in metric_names)

    def test_inject_a7(self, setup):
        from backend.generator.training_dataset import inject_a7

        rows = []
        inject_a7(rows, self.t, self.atm)
        assert len(rows) > 0


class TestGenerate:
    def test_generate_creates_file(self):
        from backend.generator.training_dataset import generate

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            output_path = Path(f.name)

        try:
            count = generate(hours=1, output_path=output_path)
            assert count > 0

            with open(output_path) as f:
                data = json.load(f)
            assert len(data) > 0
        finally:
            Path(output_path).unlink(missing_ok=True)


class TestBuildSchedule:
    def _min_gap_per_type(self, schedule):
        import datetime

        by_type: dict[str, list[datetime.datetime]] = {}
        for ts, a_type in schedule:
            by_type.setdefault(a_type, []).append(ts)
        return {
            t: min(
                (later - earlier for earlier, later in zip(sorted(v), v[1:])),
                default=None,
            )
            for t, v in by_type.items()
        }

    def test_per_type_counts_match_periods(self):
        import datetime
        import random

        from backend.generator.training_dataset import INJECTION_PERIODS, _build_schedule

        hours = 6
        start = datetime.datetime(2025, 1, 1, tzinfo=datetime.timezone.utc)
        schedule = _build_schedule(random.Random(42), hours, INJECTION_PERIODS, start)

        by_type: dict[str, int] = {}
        for _, a_type in schedule:
            by_type[a_type] = by_type.get(a_type, 0) + 1
        for a_type, period_h in INJECTION_PERIODS.items():
            expected = round(hours / period_h)
            assert by_type[a_type] == pytest.approx(expected, abs=1)

    def test_schedule_sorted_and_spacing(self):
        import datetime
        import random

        from backend.generator.training_dataset import INJECTION_PERIODS, _build_schedule

        start = datetime.datetime(2025, 1, 1, tzinfo=datetime.timezone.utc)
        schedule = _build_schedule(random.Random(42), 6, INJECTION_PERIODS, start)

        timestamps = [ts for ts, _ in schedule]
        assert timestamps == sorted(timestamps)

        gaps = self._min_gap_per_type(schedule)
        for a_type, period_h in INJECTION_PERIODS.items():
            min_gap = gaps[a_type]
            assert min_gap is not None, f"{a_type} scheduled only once"
            assert min_gap > datetime.timedelta(hours=period_h / 2), (
                f"{a_type} min gap {min_gap} too small for period {period_h}h"
            )
