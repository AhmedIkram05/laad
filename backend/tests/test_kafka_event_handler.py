"""Unit tests for event handler."""

from __future__ import annotations
from unittest.mock import MagicMock, patch

from backend.kafka.handlers.event_handler import handle_event


class MockChromaBuffer:
    def __init__(self):
        self.events_added = []

    def add_event(self, atm_id, text, timestamp, severity=None, anomaly_tag=None):
        self.events_added.append(
            {
                "atm_id": atm_id,
                "text": text,
                "timestamp": timestamp,
                "severity": severity,
                "anomaly_tag": anomaly_tag,
            }
        )


class TestHandleEvent:
    def test_valid_minimal_event_writes_to_db(self):
        msg = {
            "message_id": "msg-123",
            "timestamp": "2026-05-12T10:00:00+00:00",
            "source": "ATM_APP",
            "severity": "INFO",
        }

        with patch("backend.kafka.handlers.event_handler.get_cursor") as mock_gc:
            mock_cur = MagicMock()
            mock_gc.return_value.__enter__ = MagicMock(return_value=mock_cur)
            mock_gc.return_value.__exit__ = MagicMock(return_value=False)

            buffer = MockChromaBuffer()
            result = handle_event(msg, buffer)

            assert result is True
            mock_cur.execute.assert_called_once()
            call_args = mock_cur.execute.call_args[0][1]
            assert call_args[1] == "ATM_APP"

    def test_valid_event_with_all_fields_writes_complete_record(self):
        msg = {
            "message_id": "msg-456",
            "timestamp": "2026-05-12T10:00:00+00:00",
            "source": "ATM_APP",
            "atm_id": "ATM-GB-0001",
            "correlation_id": "corr-abc",
            "transaction_id": "txn-def",
            "event_type": "TRANSACTION_END",
            "severity": "INFO",
            "message": "Transaction completed",
            "payload": {"response_time_ms": 250},
        }

        with patch("backend.kafka.handlers.event_handler.get_cursor") as mock_gc:
            mock_cur = MagicMock()
            mock_gc.return_value.__enter__ = MagicMock(return_value=mock_cur)
            mock_gc.return_value.__exit__ = MagicMock(return_value=False)

            buffer = MockChromaBuffer()
            result = handle_event(msg, buffer)

            assert result is True
            call_args = mock_cur.execute.call_args[0][1]
            assert call_args[2] == "ATM-GB-0001"
            assert call_args[4] == "txn-def"
            assert call_args[5] == "TRANSACTION_END"
            assert buffer.events_added[0]["atm_id"] == "ATM-GB-0001"

    def test_missing_required_field_routes_to_ingestion_errors(self):
        msg = {
            "message_id": "msg-789",
            "timestamp": "2026-05-12T10:00:00+00:00",
            "source": "ATM_APP",
        }

        with patch("backend.kafka.handlers.event_handler.get_cursor") as mock_gc:
            mock_cur = MagicMock()
            mock_gc.return_value.__enter__ = MagicMock(return_value=mock_cur)
            mock_gc.return_value.__exit__ = MagicMock(return_value=False)

            buffer = MockChromaBuffer()
            result = handle_event(msg, buffer)

            assert result is False
            assert mock_cur.execute.call_count == 1
            sql = mock_cur.execute.call_args[0][0]
            assert "ingestion_errors" in sql

    def test_invalid_timestamp_routes_to_ingestion_errors(self):
        msg = {
            "message_id": "msg-bad-ts",
            "timestamp": "not-a-valid-timestamp",
            "source": "ATM_APP",
            "severity": "INFO",
        }

        with patch("backend.kafka.handlers.event_handler.get_cursor") as mock_gc:
            mock_cur = MagicMock()
            mock_gc.return_value.__enter__ = MagicMock(return_value=mock_cur)
            mock_gc.return_value.__exit__ = MagicMock(return_value=False)

            buffer = MockChromaBuffer()
            result = handle_event(msg, buffer)

            assert result is False
            assert mock_cur.execute.call_count == 1
            sql = mock_cur.execute.call_args[0][0]
            assert "ingestion_errors" in sql

    def test_db_error_returns_false(self):
        msg = {
            "message_id": "msg-dberr",
            "timestamp": "2026-05-12T10:00:00+00:00",
            "source": "ATM_APP",
            "severity": "INFO",
        }

        with patch("backend.kafka.handlers.event_handler.get_cursor") as mock_gc:
            mock_cur = MagicMock()
            mock_cur.execute.side_effect = Exception("DB error")
            mock_gc.return_value.__enter__ = MagicMock(return_value=mock_cur)
            mock_gc.return_value.__exit__ = MagicMock(side_effect=Exception("DB error"))

            buffer = MockChromaBuffer()
            result = handle_event(msg, buffer)

            assert result is False

    def test_no_atm_id_does_not_add_to_chroma(self):
        msg = {
            "message_id": "msg-no-atm",
            "timestamp": "2026-05-12T10:00:00+00:00",
            "source": "ATM_APP",
            "severity": "INFO",
            "payload": {},
        }

        with patch("backend.kafka.handlers.event_handler.get_cursor") as mock_gc:
            mock_cur = MagicMock()
            mock_gc.return_value.__enter__ = MagicMock(return_value=mock_cur)
            mock_gc.return_value.__exit__ = MagicMock(return_value=False)

            buffer = MockChromaBuffer()
            result = handle_event(msg, buffer)

            assert result is True
            assert len(buffer.events_added) == 0

    def test_null_payload_treated_as_empty_dict(self):
        msg = {
            "message_id": "msg-null-payload",
            "timestamp": "2026-05-12T10:00:00+00:00",
            "source": "ATM_APP",
            "severity": "INFO",
            "atm_id": "ATM-GB-0001",
            "payload": None,
        }

        with patch("backend.kafka.handlers.event_handler.get_cursor") as mock_gc:
            mock_cur = MagicMock()
            mock_gc.return_value.__enter__ = MagicMock(return_value=mock_cur)
            mock_gc.return_value.__exit__ = MagicMock(return_value=False)

            buffer = MockChromaBuffer()
            result = handle_event(msg, buffer)

            assert result is True

    def test_timestamp_without_tz_gets_utc_assigned(self):
        msg = {
            "message_id": "msg-naive-ts",
            "timestamp": "2026-05-12T10:00:00",
            "source": "ATM_APP",
            "severity": "INFO",
        }

        with patch("backend.kafka.handlers.event_handler.get_cursor") as mock_gc:
            mock_cur = MagicMock()
            mock_gc.return_value.__enter__ = MagicMock(return_value=mock_cur)
            mock_gc.return_value.__exit__ = MagicMock(return_value=False)

            buffer = MockChromaBuffer()
            result = handle_event(msg, buffer)

            assert result is True
            call_args = mock_cur.execute.call_args[0][1]
            assert call_args[0].tzinfo is not None
