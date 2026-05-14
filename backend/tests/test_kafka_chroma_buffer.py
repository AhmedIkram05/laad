"""Unit tests for ChromaDB buffer."""
from __future__ import annotations
import pytest
from unittest.mock import MagicMock, patch
from collections import defaultdict

from backend.kafka.chroma_buffer import ChromaBuffer, format_event_text


class TestFormatEventText:
    def test_basic_formatting(self):
        msg = {
            "timestamp": "2026-05-12T10:00:00+00:00",
            "source": "ATM_APP",
            "event_type": "ACTIVITY",
            "message": "User session active",
            "payload": {"location_code": "LOC-001"},
        }
        text = format_event_text(msg)
        assert "2026-05-12" in text
        assert "ATM_APP" in text
        assert "ACTIVITY" in text
        assert "User session active" in text
        assert "location_code=LOC-001" in text

    def test_payload_key_value_limit(self):
        msg = {
            "timestamp": "2026-05-12T10:00:00+00:00",
            "source": "ATM_APP",
            "event_type": "LOG",
            "message": "Test",
            "payload": {f"key{i}": f"val{i}" for i in range(20)},
        }
        text = format_event_text(msg)
        for i in range(5):
            assert f"key{i}=val{i}" in text
        for i in range(10, 20):
            assert f"key{i}=val{i}" not in text

    def test_missing_fields_handled_gracefully(self):
        msg = {}
        text = format_event_text(msg)
        assert "[UNKNOWN]" in text

    def test_null_payload_skipped(self):
        msg = {
            "timestamp": "2026-05-12T10:00:00+00:00",
            "source": "ATM_APP",
            "event_type": "LOG",
            "message": "Test",
            "payload": None,
        }
        text = format_event_text(msg)
        assert "Test" in text


class TestChromaBufferInit:
    def test_init_failure_graceful(self):
        with patch("backend.kafka.chroma_buffer._build_chroma_client") as mock_chroma:
            mock_chroma.side_effect = Exception("ChromaDB unavailable")
            buffer = ChromaBuffer()
            assert buffer._ready is False

    def test_init_success(self):
        mock_collection = MagicMock()
        mock_client = MagicMock()
        mock_client.get_or_create_collection.return_value = mock_collection

        with patch("backend.kafka.chroma_buffer._build_chroma_client", return_value=mock_client):
            with patch("backend.kafka.chroma_buffer._build_embeddings", return_value=MagicMock()):
                with patch("backend.kafka.chroma_buffer._build_chunker", return_value=MagicMock()):
                    buffer = ChromaBuffer()
                    assert buffer._ready is True
                    assert buffer._collection is mock_collection


class TestChromaBufferAddEvent:
    def test_not_ready_does_nothing(self):
        with patch("backend.kafka.chroma_buffer._build_chroma_client") as mock_chroma:
            mock_chroma.side_effect = Exception("fail")
            buffer = ChromaBuffer()
            buffer.add_event("ATM-GB-0001", "some text", "2026-05-12T10:00:00Z")
            assert len(buffer._buffers) == 0

    def test_add_event_accumulates_in_buffer(self):
        mock_collection = MagicMock()
        mock_client = MagicMock()
        mock_client.get_or_create_collection.return_value = mock_collection

        mock_chunker = MagicMock()
        mock_chunker.create_documents.return_value = []

        with patch("backend.kafka.chroma_buffer._build_chroma_client", return_value=mock_client):
            with patch("backend.kafka.chroma_buffer._build_embeddings", return_value=MagicMock()):
                with patch("backend.kafka.chroma_buffer._build_chunker", return_value=mock_chunker):
                    with patch("backend.kafka.chroma_buffer.WINDOW_SIZE", 3):
                        buffer = ChromaBuffer()
                        buffer._ready = True
                        buffer._client = mock_client
                        buffer._collection = mock_collection
                        buffer._buffers = defaultdict(list)
                        buffer._chunker = mock_chunker

                        buffer.add_event("ATM-GB-0001", "event 1", "2026-05-12T10:00:00Z")
                        buffer.add_event("ATM-GB-0001", "event 2", "2026-05-12T10:01:00Z")
                        assert len(buffer._buffers["ATM-GB-0001"]) == 2

    def test_add_event_triggers_flush_at_window_size(self):
        mock_collection = MagicMock()
        mock_client = MagicMock()
        mock_client.get_or_create_collection.return_value = mock_collection

        mock_chunker = MagicMock()
        mock_doc = MagicMock()
        mock_doc.page_content = "chunked text"
        mock_chunker.create_documents.return_value = [mock_doc]

        with patch("backend.kafka.chroma_buffer._build_chroma_client", return_value=mock_client):
            with patch("backend.kafka.chroma_buffer._build_embeddings", return_value=MagicMock()):
                with patch("backend.kafka.chroma_buffer._build_chunker", return_value=mock_chunker):
                    with patch("backend.kafka.chroma_buffer.WINDOW_SIZE", 2):
                        buffer = ChromaBuffer()
                        buffer._ready = True
                        buffer._client = mock_client
                        buffer._collection = mock_collection
                        buffer._buffers = defaultdict(list)
                        buffer._chunker = mock_chunker

                        buffer.add_event("ATM-GB-0001", "event 1", "2026-05-12T10:00:00Z")
                        assert len(buffer._buffers["ATM-GB-0001"]) == 1

                        buffer.add_event("ATM-GB-0001", "event 2", "2026-05-12T10:01:00Z")
                        assert "ATM-GB-0001" not in buffer._buffers
                        mock_collection.upsert.assert_called_once()


class TestChromaBufferFlush:
    def test_flush_all_emits_all_buffers(self):
        mock_collection = MagicMock()
        mock_client = MagicMock()
        mock_client.get_or_create_collection.return_value = mock_collection

        mock_chunker = MagicMock()
        mock_doc = MagicMock()
        mock_doc.page_content = "chunked text"
        mock_chunker.create_documents.return_value = [mock_doc]

        with patch("backend.kafka.chroma_buffer._build_chroma_client", return_value=mock_client):
            with patch("backend.kafka.chroma_buffer._build_embeddings", return_value=MagicMock()):
                with patch("backend.kafka.chroma_buffer._build_chunker", return_value=mock_chunker):
                    buffer = ChromaBuffer()
                    buffer._ready = True
                    buffer._client = mock_client
                    buffer._collection = mock_collection
                    buffer._buffers = defaultdict(list)
                    buffer._buffers["ATM-GB-0001"] = [("text1", "ts1"), ("text2", "ts2")]
                    buffer._buffers["ATM-GB-0002"] = [("text3", "ts3")]
                    buffer._chunker = mock_chunker

                    buffer.flush_all()

                    assert "ATM-GB-0001" not in buffer._buffers
                    assert "ATM-GB-0002" not in buffer._buffers
                    assert mock_collection.upsert.call_count == 2

    def test_flush_all_handles_empty_buffers(self):
        mock_collection = MagicMock()
        mock_client = MagicMock()
        mock_client.get_or_create_collection.return_value = mock_collection

        with patch("backend.kafka.chroma_buffer._build_chroma_client", return_value=mock_client):
            with patch("backend.kafka.chroma_buffer._build_embeddings", return_value=MagicMock()):
                with patch("backend.kafka.chroma_buffer._build_chunker", return_value=MagicMock()):
                    buffer = ChromaBuffer()
                    buffer._ready = True
                    buffer._client = mock_client
                    buffer._collection = mock_collection
                    buffer._buffers = defaultdict(list)

                    buffer.flush_all()
                    mock_collection.upsert.assert_not_called()

    def test_flush_all_handles_upsert_error(self):
        mock_collection = MagicMock()
        mock_collection.upsert.side_effect = Exception("ChromaDB error")
        mock_client = MagicMock()
        mock_client.get_or_create_collection.return_value = mock_collection

        mock_chunker = MagicMock()
        mock_doc = MagicMock()
        mock_doc.page_content = "text"
        mock_chunker.create_documents.return_value = [mock_doc]

        with patch("backend.kafka.chroma_buffer._build_chroma_client", return_value=mock_client):
            with patch("backend.kafka.chroma_buffer._build_embeddings", return_value=MagicMock()):
                with patch("backend.kafka.chroma_buffer._build_chunker", return_value=mock_chunker):
                    buffer = ChromaBuffer()
                    buffer._ready = True
                    buffer._client = mock_client
                    buffer._collection = mock_collection
                    buffer._buffers = defaultdict(list)
                    buffer._buffers["ATM-GB-0001"] = [("text", "ts")]
                    buffer._chunker = mock_chunker

                    buffer.flush_all()
                    assert "ATM-GB-0001" not in buffer._buffers