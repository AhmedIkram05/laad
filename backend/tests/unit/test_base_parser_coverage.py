"""Coverage for backend.src.ingestion.parsers.base_parser.

Covers _upsert_atm_reference caching/flush trigger, _flush_ref_buffer,
validate_sample branches, insert_ingestion_error, and both
EventDataParser/MetricDataParser flush paths — all with mocked DB.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from backend.src.ingestion.parsers.base_parser import (
    BaseParser,
    EventDataParser,
    MetricDataParser,
)


class _MemParser(BaseParser):
    def parse_line(self, line: str):
        s = line.strip()
        if s == "BAD":
            raise ValueError("malformed")
        if s == "NONE":
            return None
        return {"raw": s}


class _EventParser(EventDataParser):
    def parse_line(self, line: str):
        return {"timestamp": "t", "source": "ATM_APP", "atm_id": "A1"}


class _MetricParser(MetricDataParser):
    def parse_line(self, line: str):
        return {"timestamp": "t", "source": "CLOUD", "entity_id": "E1"}


def _fake_conn():
    conn = MagicMock()
    cur = MagicMock()
    cur.__enter__.return_value = cur
    cur.__exit__.return_value = False
    conn.cursor.return_value = cur
    return conn, cur


class TestInit:
    def test_db_path_from_env(self, monkeypatch):
        monkeypatch.setenv("DB_PATH", "/tmp/x.db")
        p = _MemParser()
        assert p.db_path == "/tmp/x.db"

    def test_batch_size_coerced_to_int(self):
        p = _MemParser(batch_size="3")
        assert p.batch_size == 3


class TestUpsertRef:
    def test_no_update_when_same_values(self):
        p = _MemParser(batch_size=10)
        p._upsert_atm_reference("ATM-1", os_version="v1")
        assert len(p.ref_buffer) == 1
        # same value again -> no new entry
        p._upsert_atm_reference("ATM-1", os_version="v1")
        assert len(p.ref_buffer) == 1

    def test_location_code_update(self):
        p = _MemParser(batch_size=10)
        p._upsert_atm_reference("ATM-2", location_code="L1")
        assert p.ref_buffer == [("ATM-2", None, "L1")]
        # no-op when nothing new
        p._upsert_atm_reference("ATM-2")
        assert len(p.ref_buffer) == 1

    def test_batch_trigger_flushes_with_conn(self):
        p = _MemParser(batch_size=1)
        conn, _ = _fake_conn()
        with (
            patch("backend.src.database.connection.get_conn", return_value=conn),
            patch("backend.src.database.connection.release_conn") as mock_rel,
            patch("backend.src.ingestion.write_helper.write_batch") as mock_wb,
        ):
            p._upsert_atm_reference("ATM-3", os_version="v9")
            assert mock_wb.called
            assert mock_rel.called
            assert p.ref_buffer == []

    def test_batch_trigger_release_failure_swallowed(self):
        p = _MemParser(batch_size=1)
        conn, _ = _fake_conn()
        with (
            patch("backend.src.database.connection.get_conn", return_value=conn),
            patch(
                "backend.src.database.connection.release_conn",
                side_effect=RuntimeError("gone"),
            ),
            patch("backend.src.ingestion.write_helper.write_batch"),
        ):
            # must not raise
            p._upsert_atm_reference("ATM-4", os_version="v2")
            assert p.ref_buffer == []


class TestFlushRefBuffer:
    def test_empty_returns_without_write(self):
        p = _MemParser()
        conn, _ = _fake_conn()
        with patch("backend.src.ingestion.write_helper.write_batch") as mock_wb:
            p._flush_ref_buffer(conn)
            mock_wb.assert_not_called()

    def test_success_clears_buffer(self):
        p = _MemParser()
        p.ref_buffer = [("A", "v", "L")]
        conn, _ = _fake_conn()
        with patch("backend.src.ingestion.write_helper.write_batch") as mock_wb:
            p._flush_ref_buffer(conn)
            mock_wb.assert_called_once()
            assert p.ref_buffer == []

    def test_write_failure_logged_and_cleared(self):
        p = _MemParser()
        p.ref_buffer = [("A", "v", "L")]
        conn, _ = _fake_conn()
        with patch(
            "backend.src.ingestion.write_helper.write_batch",
            side_effect=RuntimeError("db down"),
        ):
            p._flush_ref_buffer(conn)  # must not raise
            assert p.ref_buffer == []


class TestValidateSample:
    def test_init_failure_returns_true(self, monkeypatch):
        class _Boom(BaseParser):
            def __init__(self, *a, **k):
                raise RuntimeError("nope")

            def parse_line(self, line):
                return {}

        assert _Boom.validate_sample("/nonexistent") is True

    def test_open_failure_returns_false(self):
        assert _MemParser.validate_sample("/definitely/not/here.csv") is False

    def test_empty_file_returns_true(self, tmp_path):
        f = tmp_path / "s.csv"
        f.write_text("header\n")
        assert _MemParser.validate_sample(str(f)) is True

    def test_all_good_returns_true(self, tmp_path):
        f = tmp_path / "s.csv"
        f.write_text("header\na\nb\nc\n")
        assert _MemParser.validate_sample(str(f), sample_lines=10) is True

    def test_all_bad_returns_false(self, tmp_path):
        f = tmp_path / "s.csv"
        f.write_text("header\nBAD\nBAD\nBAD\n")
        assert _MemParser.validate_sample(str(f), sample_lines=10) is False

    def test_blank_lines_skipped_and_limit_respected(self, tmp_path):
        f = tmp_path / "s.csv"
        f.write_text("header\n\n   \ngood\nBAD\n")
        # 1 good + 1 bad = 50% fail > 30% default -> False
        assert _MemParser.validate_sample(str(f), sample_lines=10) is False
        # higher threshold passes
        assert (
            _MemParser.validate_sample(str(f), sample_lines=10, max_fail_ratio=0.6)
            is True
        )

    def test_sample_lines_cap(self, tmp_path):
        f = tmp_path / "s.csv"
        f.write_text("header\n" + "good\n" * 20 + "BAD\n" * 20)
        # only first 2 sampled, both good -> True even though file mostly bad
        assert _MemParser.validate_sample(str(f), sample_lines=2) is True


class TestInsertError:
    def test_success_writes_and_releases(self):
        p = _MemParser()
        conn, cur = _fake_conn()
        with (
            patch("backend.src.database.connection.get_conn", return_value=conn),
            patch("backend.src.database.connection.release_conn") as mock_rel,
        ):
            p.insert_ingestion_error("detail", "raw", source="SRC")
            assert cur.execute.called
            assert conn.commit.called
            mock_rel.assert_called_once_with(conn)

    def test_db_failure_never_raises(self):
        p = _MemParser()
        with patch(
            "backend.src.database.connection.get_conn",
            side_effect=RuntimeError("down"),
        ):
            p.insert_ingestion_error("d", "r")  # must not raise

    def test_release_failure_swallowed(self):
        p = _MemParser()
        conn, _ = _fake_conn()
        with (
            patch("backend.src.database.connection.get_conn", return_value=conn),
            patch(
                "backend.src.database.connection.release_conn",
                side_effect=RuntimeError("gone"),
            ),
        ):
            p.insert_ingestion_error("d", "r")  # must not raise


class TestProcessLine:
    def test_none_result_returns_true_without_buffer(self):
        p = _MemParser(batch_size=10)
        assert p.process_line("NONE") is True
        assert p._buffer == []

    def test_buffer_flush_on_batch_size(self):
        p = _MemParser(batch_size=2)
        with patch.object(p, "flush") as mock_flush:
            p.process_line("a")
            assert not mock_flush.called
            p.process_line("b")
            mock_flush.assert_called_once()

    def test_base_flush_clears(self):
        p = _MemParser()
        p._buffer = [{"x": 1}]
        p.flush()
        assert p._buffer == []


class TestEventFlush:
    def test_empty_no_db(self):
        p = _EventParser()
        with patch("backend.src.database.connection.get_conn") as mock_gc:
            p.flush()
            mock_gc.assert_not_called()

    def test_success_writes_and_clears(self):
        p = _EventParser()
        p._buffer = [
            {
                "timestamp": "t",
                "source": "ATM_APP",
                "atm_id": "A1",
                "correlation_id": "c",
                "transaction_id": "tx",
                "event_type": "E",
                "severity": "INFO",
                "message": "m",
                "payload": "{}",
            }
        ]
        conn, _ = _fake_conn()
        with (
            patch("backend.src.database.connection.get_conn", return_value=conn),
            patch("backend.src.database.connection.release_conn"),
            patch("backend.src.ingestion.write_helper.write_batch") as mock_wb,
            patch.object(p, "_flush_ref_buffer") as mock_ref,
        ):
            p.flush()
            mock_wb.assert_called_once()
            mock_ref.assert_called_once_with(conn)
            assert p._buffer == []

    def test_failure_records_ingestion_errors(self):
        p = _EventParser()
        p._buffer = [{"timestamp": "t", "source": "ATM_APP"}]
        with (
            patch(
                "backend.src.database.connection.get_conn",
                side_effect=RuntimeError("down"),
            ),
            patch.object(p, "insert_ingestion_error") as mock_err,
        ):
            p.flush()
            mock_err.assert_called()
            assert p._buffer == []

    def test_failure_inner_insert_raises_is_swallowed(self):
        p = _EventParser()
        p._buffer = [{"timestamp": "t", "source": "ATM_APP"}]
        with (
            patch(
                "backend.src.database.connection.get_conn",
                side_effect=RuntimeError("down"),
            ),
            patch.object(
                p, "insert_ingestion_error", side_effect=RuntimeError("also down")
            ),
        ):
            p.flush()  # must not raise
            assert p._buffer == []

    def test_release_failure_swallowed(self):
        p = _EventParser()
        p._buffer = [{"timestamp": "t", "source": "ATM_APP"}]
        conn, _ = _fake_conn()
        with (
            patch("backend.src.database.connection.get_conn", return_value=conn),
            patch(
                "backend.src.database.connection.release_conn",
                side_effect=RuntimeError("gone"),
            ),
            patch("backend.src.ingestion.write_helper.write_batch"),
        ):
            p.flush()
            assert p._buffer == []


class TestMetricFlush:
    def test_empty_no_db(self):
        p = _MetricParser()
        with patch("backend.src.database.connection.get_conn") as mock_gc:
            p.flush()
            mock_gc.assert_not_called()

    def test_success(self):
        p = _MetricParser()
        p._buffer = [
            {
                "timestamp": "t",
                "source": "CLOUD",
                "entity_id": "E1",
                "metric_name": "m",
                "metric_value": 1.5,
                "payload": "{}",
            }
        ]
        conn, _ = _fake_conn()
        with (
            patch("backend.src.database.connection.get_conn", return_value=conn),
            patch("backend.src.database.connection.release_conn"),
            patch("backend.src.ingestion.write_helper.write_batch") as mock_wb,
            patch.object(p, "_flush_ref_buffer") as mock_ref,
        ):
            p.flush()
            mock_wb.assert_called_once()
            mock_ref.assert_called_once_with(conn)
            assert p._buffer == []

    def test_failure_records_errors(self):
        p = _MetricParser()
        p._buffer = [{"timestamp": "t", "source": "METRIC"}]
        with (
            patch(
                "backend.src.database.connection.get_conn",
                side_effect=RuntimeError("down"),
            ),
            patch.object(p, "insert_ingestion_error") as mock_err,
        ):
            p.flush()
            mock_err.assert_called()
            assert p._buffer == []

    def test_failure_inner_insert_raises_swallowed(self):
        p = _MetricParser()
        p._buffer = [{"timestamp": "t"}]
        with (
            patch(
                "backend.src.database.connection.get_conn",
                side_effect=RuntimeError("down"),
            ),
            patch.object(p, "insert_ingestion_error", side_effect=RuntimeError("x")),
        ):
            p.flush()
            assert p._buffer == []

    def test_release_failure_swallowed(self):
        p = _MetricParser()
        p._buffer = [{"timestamp": "t", "source": "M"}]
        conn, _ = _fake_conn()
        with (
            patch("backend.src.database.connection.get_conn", return_value=conn),
            patch(
                "backend.src.database.connection.release_conn",
                side_effect=RuntimeError("gone"),
            ),
            patch("backend.src.ingestion.write_helper.write_batch"),
        ):
            p.flush()
            assert p._buffer == []

    def test_default_source_when_missing(self):
        p = _MetricParser()
        p._buffer = [{"timestamp": "t"}]
        with (
            patch(
                "backend.src.database.connection.get_conn",
                side_effect=RuntimeError("down"),
            ),
            patch.object(p, "insert_ingestion_error") as mock_err,
        ):
            p.flush()
            _, kwargs = mock_err.call_args
            assert kwargs.get(
                "source",
                mock_err.call_args[0][2] if len(mock_err.call_args[0]) > 2 else None,
            ) in (None, "METRIC")
            assert p._buffer == []
