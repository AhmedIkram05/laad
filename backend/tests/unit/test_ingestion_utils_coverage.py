"""Fallback-branch coverage for backend.src.ingestion.utils.parse_to_utc_iso.

Existing test_ingestion_utils.py covers the dateutil-preferred path.
This file forces the stdlib fallback (dateutil stubbed out) plus the
outer-exception and None-input branches — lines 35-62 in utils.py.
"""

from __future__ import annotations

from datetime import timezone

import backend.src.ingestion.utils as utils
from backend.src.ingestion.utils import parse_to_utc_iso


def _disable_dateutil(monkeypatch):
    monkeypatch.setattr(utils, "_dateutil_parser", None)
    monkeypatch.setattr(utils, "_dateutil_tz", None)


class TestFallbackIso:
    def test_zulu_via_fallback(self, monkeypatch):
        _disable_dateutil(monkeypatch)
        out = parse_to_utc_iso("2026-03-05T09:15:00Z")
        assert out is not None
        assert out.endswith("+00:00")
        assert "09:15:00" in out

    def test_naive_treated_as_utc_fallback(self, monkeypatch):
        _disable_dateutil(monkeypatch)
        out = parse_to_utc_iso("2026-03-05T09:15:00")
        assert out is not None
        assert out.endswith("+00:00")

    def test_offset_converted_to_utc_fallback(self, monkeypatch):
        _disable_dateutil(monkeypatch)
        out = parse_to_utc_iso("2026-03-05T09:15:00+05:00")
        assert out is not None
        assert "04:15:00" in out
        assert out.endswith("+00:00")

    def test_millis_zulu_fallback(self, monkeypatch):
        _disable_dateutil(monkeypatch)
        out = parse_to_utc_iso("2026-03-05T09:15:00.123456Z")
        assert out is not None
        assert out.endswith("+00:00")

    def test_fallback_uses_dateutil_tz_when_present(self, monkeypatch):
        # _dateutil_parser None but _dateutil_tz present -> line 45-46 branch.
        monkeypatch.setattr(utils, "_dateutil_parser", None)
        import dateutil.tz as dt_tz  # type: ignore

        monkeypatch.setattr(utils, "_dateutil_tz", dt_tz)
        out = parse_to_utc_iso("2026-03-05T09:15:00Z")
        assert out is not None
        assert out.endswith("+00:00")

    def test_legacy_tz_without_colon_hits_strptime_loop(self, monkeypatch):
        # fromisoformat rejects +0000 (no colon); strptime %z accepts it.
        _disable_dateutil(monkeypatch)
        out = parse_to_utc_iso("2026-03-05T09:15:00+0000")
        assert out is not None
        assert out.endswith("+00:00")

    def test_legacy_strptime_success_when_fromisoformat_fails(self, monkeypatch):
        from datetime import datetime as _real_dt

        _disable_dateutil(monkeypatch)

        class _FakeDT(_real_dt):
            @classmethod
            def fromisoformat(cls, _s):
                raise ValueError("forced for legacy coverage")

        monkeypatch.setattr(utils, "datetime", _FakeDT)
        out = parse_to_utc_iso("2026-03-05 09:15:00")
        assert out is not None
        assert out.endswith("+00:00")

    def test_invalid_returns_none_via_fallback(self, monkeypatch):
        _disable_dateutil(monkeypatch)
        assert parse_to_utc_iso("not-a-date") is None

    def test_none_input_returns_none(self):
        assert parse_to_utc_iso(None) is None  # type: ignore[arg-type]
        assert parse_to_utc_iso("") is None

    def test_dateutil_tz_none_with_naive_dt_returns_none(self, monkeypatch):
        # dateutil present but tz module missing: naive dt can't be zoned,
        # AttributeError inside try -> outer except -> None.
        from unittest.mock import MagicMock
        from datetime import datetime as _datetime

        mock_parser = MagicMock()
        mock_parser.parse.return_value = _datetime(2026, 3, 5, 9, 15, 0)
        monkeypatch.setattr(utils, "_dateutil_parser", mock_parser)
        monkeypatch.setattr(utils, "_dateutil_tz", None)
        assert parse_to_utc_iso("2026-03-05T09:15:00") is None

    def test_dateutil_parse_raises_returns_none(self, monkeypatch):
        from unittest.mock import MagicMock

        mock_parser = MagicMock()
        mock_parser.side_effect = None
        mock_parser.parse.side_effect = ValueError("boom")
        import dateutil.tz as dt_tz  # type: ignore

        monkeypatch.setattr(utils, "_dateutil_parser", mock_parser)
        monkeypatch.setattr(utils, "_dateutil_tz", dt_tz)
        assert parse_to_utc_iso("2026-03-05T09:15:00Z") is None

    def test_utc_conversion_uses_stdlib_timezone(self, monkeypatch):
        _disable_dateutil(monkeypatch)
        out = parse_to_utc_iso("2026-03-05T09:15:00+00:00")
        assert out is not None
        # stdlib timezone.utc isoformat ends with +00:00
        assert timezone.utc is not None
        assert "+00:00" in out
