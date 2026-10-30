"""Unit tests for metric handler."""

from __future__ import annotations
from unittest.mock import MagicMock, patch

from backend.kafka.handlers.metric_handler import handle_metric

import pytest

pytestmark = pytest.mark.kafka


class TestHandleMetric:
    def test_valid_minimal_metric_writes_to_db(self):
        msg = {
            "message_id": "m-123",
            "timestamp": "2026-05-12T10:00:00+00:00",
            "source": "PROMETHEUS",
            "entity_id": "pod-0",
            "metric_name": "cpu_usage",
            "metric_value": 0.75,
            "payload": {},
        }

        with patch("backend.kafka.handlers.metric_handler.get_cursor") as mock_gc:
            mock_cur = MagicMock()
            mock_gc.return_value.__enter__ = MagicMock(return_value=mock_cur)
            mock_gc.return_value.__exit__ = MagicMock(return_value=False)

            result = handle_metric(msg)

            assert result is True
            mock_cur.execute.assert_called_once()
            call_args = mock_cur.execute.call_args[0][1]
            assert call_args[2] == "pod-0"
            assert call_args[3] == "cpu_usage"
            assert call_args[4] == 0.75

    def test_valid_metric_with_all_fields(self):
        msg = {
            "message_id": "m-456",
            "timestamp": "2026-05-12T10:00:00+00:00",
            "source": "CLOUD",
            "entity_id": "terminal-handler-pod-0",
            "metric_name": "container/cpu/usage_time",
            "metric_value": 0.85,
            "payload": {"pod_name": "terminal-handler-pod-0"},
        }

        with patch("backend.kafka.handlers.metric_handler.get_cursor") as mock_gc:
            mock_cur = MagicMock()
            mock_gc.return_value.__enter__ = MagicMock(return_value=mock_cur)
            mock_gc.return_value.__exit__ = MagicMock(return_value=False)

            result = handle_metric(msg)

            assert result is True

    def test_non_numeric_metric_value_routes_to_ingestion_errors(self):
        msg = {
            "message_id": "m-bad-val",
            "timestamp": "2026-05-12T10:00:00+00:00",
            "source": "PROMETHEUS",
            "entity_id": "pod-0",
            "metric_name": "cpu",
            "metric_value": "not-a-number",
        }

        with patch("backend.kafka.handlers.metric_handler.get_cursor") as mock_gc:
            mock_cur = MagicMock()
            mock_gc.return_value.__enter__ = MagicMock(return_value=mock_cur)
            mock_gc.return_value.__exit__ = MagicMock(return_value=False)

            result = handle_metric(msg)

            assert result is False

    def test_invalid_timestamp_routes_to_ingestion_errors(self):
        msg = {
            "message_id": "m-bad-ts",
            "timestamp": "invalid-timestamp",
            "source": "PROMETHEUS",
            "entity_id": "pod-0",
            "metric_name": "cpu",
            "metric_value": 0.5,
        }

        with patch("backend.kafka.handlers.metric_handler.get_cursor") as mock_gc:
            mock_cur = MagicMock()
            mock_gc.return_value.__enter__ = MagicMock(return_value=mock_cur)
            mock_gc.return_value.__exit__ = MagicMock(return_value=False)

            result = handle_metric(msg)

            assert result is False

    def test_db_error_returns_false(self):
        msg = {
            "message_id": "m-dberr",
            "timestamp": "2026-05-12T10:00:00+00:00",
            "source": "PROMETHEUS",
            "entity_id": "pod-0",
            "metric_name": "cpu",
            "metric_value": 0.5,
        }

        with patch("backend.kafka.handlers.metric_handler.get_cursor") as mock_gc:
            mock_cur = MagicMock()
            mock_cur.execute.side_effect = Exception("DB error")
            mock_gc.return_value.__enter__ = MagicMock(return_value=mock_cur)
            mock_gc.return_value.__exit__ = MagicMock(side_effect=Exception("DB error"))

            result = handle_metric(msg)

            assert result is False

    def test_null_payload_treated_as_empty_dict(self):
        msg = {
            "message_id": "m-null-payload",
            "timestamp": "2026-05-12T10:00:00+00:00",
            "source": "PROMETHEUS",
            "entity_id": "pod-0",
            "metric_name": "cpu",
            "metric_value": 0.5,
            "payload": None,
        }

        with patch("backend.kafka.handlers.metric_handler.get_cursor") as mock_gc:
            mock_cur = MagicMock()
            mock_gc.return_value.__enter__ = MagicMock(return_value=mock_cur)
            mock_gc.return_value.__exit__ = MagicMock(return_value=False)

            result = handle_metric(msg)

            assert result is True

    def test_metric_value_integer_converted_to_float(self):
        msg = {
            "message_id": "m-int",
            "timestamp": "2026-05-12T10:00:00+00:00",
            "source": "PROMETHEUS",
            "entity_id": "pod-0",
            "metric_name": "count",
            "metric_value": 42,
        }

        with patch("backend.kafka.handlers.metric_handler.get_cursor") as mock_gc:
            mock_cur = MagicMock()
            mock_gc.return_value.__enter__ = MagicMock(return_value=mock_cur)
            mock_gc.return_value.__exit__ = MagicMock(return_value=False)

            result = handle_metric(msg)

            assert result is True
            call_args = mock_cur.execute.call_args[0][1]
            assert call_args[4] == 42.0

    def test_offset_timestamp_bucketed_in_utc(self):
        # 2026-05-12T03:30+05:30 == 2026-05-11T22:00Z — the analytics hour
        # bucket must be derived from UTC, not the producer's local offset.
        msg = {
            "message_id": "m-tz",
            "timestamp": "2026-05-12T03:30:00+05:30",
            "source": "PROMETHEUS",
            "entity_id": "pod-0",
            "metric_name": "cpu",
            "metric_value": 1.0,
        }

        with (
            patch("backend.kafka.handlers.metric_handler.get_cursor") as mock_gc,
            patch(
                "backend.kafka.handlers.metric_handler.increment_event_counter"
            ) as mock_incr,
        ):
            mock_cur = MagicMock()
            mock_gc.return_value.__enter__ = MagicMock(return_value=mock_cur)
            mock_gc.return_value.__exit__ = MagicMock(return_value=False)

            result = handle_metric(msg)

            assert result is True
            mock_incr.assert_called_once_with("PROMETHEUS", "2026-05-11T22")
