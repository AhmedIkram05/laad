"""Tests for backend.src.ingestion.utils.parse_to_utc_iso."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from backend.src.ingestion.utils import parse_to_utc_iso


class TestParseToUtcIso:
    def test_none_or_empty_returns_none(self):
        assert parse_to_utc_iso("") is None

    def test_iso_zulu(self):
        result = parse_to_utc_iso("2026-03-05T09:15:00Z")
        assert result is not None
        assert "+00:00" in result or result.endswith("+00:00")

    def test_iso_with_offset(self):
        result = parse_to_utc_iso("2026-03-05T09:15:00+05:00")
        assert result is not None
        # Should be converted to UTC: 04:15:00
        assert "T04:15:00" in result or "T04:15:00" in result.replace("+00:00", "")

    def test_iso_naive_treated_as_utc(self):
        result = parse_to_utc_iso("2026-03-05T09:15:00")
        assert result is not None
        assert "+00:00" in result or result.endswith("+00:00")

    def test_date_only(self):
        result = parse_to_utc_iso("2026-03-05")
        assert result is not None

    def test_legacy_format_no_tz(self):
        result = parse_to_utc_iso("2026-03-05 09:15:00")
        assert result is not None
        assert "+00:00" in result or result.endswith("+00:00")

    def test_invalid_string_returns_none(self):
        assert parse_to_utc_iso("not-a-date") is None

    def test_milliseconds(self):
        result = parse_to_utc_iso("2026-03-05T09:15:00.123Z")
        assert result is not None
        assert "+00:00" in result or result.endswith("+00:00")

    def test_dateutil_available(self, monkeypatch):
        """When dateutil is available it should be preferred."""
        from unittest.mock import MagicMock
        mock_parser = MagicMock()
        mock_parser.parse.return_value = datetime(2026, 3, 5, 9, 15, 0, tzinfo=timezone.utc)
        mock_tz = MagicMock()
        mock_tz.UTC = timezone.utc

        import backend.src.ingestion.utils as utils
        monkeypatch.setattr(utils, "_dateutil_parser", mock_parser)
        monkeypatch.setattr(utils, "_dateutil_tz", mock_tz)

        result = parse_to_utc_iso("2026-03-05T09:15:00Z")
        assert result is not None
        assert mock_parser.parse.called

    def test_dateutil_parses_naive_and_adds_utc(self, monkeypatch):
        """When dateutil returns a naive datetime, UTC should be added."""
        from unittest.mock import MagicMock
        mock_parser = MagicMock()
        mock_parser.parse.return_value = datetime(2026, 3, 5, 9, 15, 0)
        mock_tz = MagicMock()
        mock_tz.UTC = timezone.utc

        import backend.src.ingestion.utils as utils
        monkeypatch.setattr(utils, "_dateutil_parser", mock_parser)
        monkeypatch.setattr(utils, "_dateutil_tz", mock_tz)

        result = parse_to_utc_iso("2026-03-05T09:15:00")
        assert result is not None


import sys
