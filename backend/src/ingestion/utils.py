"""Utility helpers for ingestion pipeline."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
import logging

try:
    from dateutil import parser as _dateutil_parser
    from dateutil import tz as _dateutil_tz
except Exception:  # pragma: no cover - optional dependency
    _dateutil_parser = None
    _dateutil_tz = None

logger = logging.getLogger(__name__)


def parse_to_utc_iso(timestamp_str: str) -> Optional[str]:
    """Parse an input timestamp string to UTC ISO-8601 format.

    Returns the ISO string (e.g. '2026-03-05T09:15:00+00:00') or None on failure.
    This helper prefers `python-dateutil` when available for robustness.
    """
    if not timestamp_str:
        return None
    try:
        if _dateutil_parser is not None:
            dt = _dateutil_parser.parse(timestamp_str)
            if _dateutil_tz is not None and dt.tzinfo is None:
                dt = dt.replace(tzinfo=_dateutil_tz.UTC)
            dt_utc = dt.astimezone(_dateutil_tz.UTC)
            return dt_utc.isoformat()
        # Fallback: handle common ISO formats including milliseconds and trailing Z
        ts = timestamp_str
        if ts.endswith("Z"):
            ts = ts[:-1] + "+00:00"
        try:
            # datetime.fromisoformat can parse YYYY-MM-DDTHH:MM:SS[.mmmmmm]+HH:MM
            dt = datetime.fromisoformat(ts)
            # If naive, treat as UTC
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            # Return ISO with offset (use dateutil tz if present otherwise timezone.utc)
            if _dateutil_tz is not None:
                return dt.astimezone(_dateutil_tz.UTC).isoformat()
            return dt.astimezone(timezone.utc).isoformat()
        except Exception:
            # As a last resort, try a few legacy formats
            for fmt in (
                "%Y-%m-%dT%H:%M:%S%z",
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%dT%H:%M:%S",
            ):
                try:
                    dt = datetime.strptime(timestamp_str, fmt)
                    # Treat naive parsed times as UTC
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    return dt.astimezone(timezone.utc).isoformat()
                except Exception:
                    continue
    except Exception:
        logger.exception("Failed to parse timestamp: %s", timestamp_str)
    return None
