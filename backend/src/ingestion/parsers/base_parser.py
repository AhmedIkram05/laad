"""Base ingestor/parser utilities.

Provides a resilient BaseParser class that catches parsing errors and
records bad inputs to the `ingestion_errors` table. Designed to be
subclassed for source-specific parsers.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone
import os
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class BaseParser(ABC):
    """Abstract base parser for ingestion.

    Subclasses implement `parse_line` which should either return a
    dictionary representing the parsed row (for buffering/insertion)
    or raise an exception for malformed input.
    """

    def __init__(self, db_path: str | None = None, batch_size: int = 500):
        self.db_path = db_path or os.getenv("DB_PATH") or ""
        self.batch_size = int(batch_size)
        self._buffer: list[Dict[str, Any]] = []

        # Buffer for ATM reference data updates
        self._atm_ref_cache: Dict[str, dict] = {}
        self.ref_buffer: list[tuple] = []

    @abstractmethod
    def parse_line(self, line: str) -> Optional[Dict[str, Any]]:
        """Parse a single input line and return a mapping or raise on error."""

    def process_line(self, line: str, source: str = "UNKNOWN") -> bool:
        """Safely process a single line.

        Returns True if parsing succeeded (even if parse_line returns None),
        or False if a parsing exception occurred (and the error was recorded).
        """
        try:
            parsed = self.parse_line(line)
            if parsed:
                self._buffer.append(parsed)
                if len(self._buffer) >= self.batch_size:
                    self.flush()
            return True
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("Failed to parse line")
            self.insert_ingestion_error(str(exc), line, source=source)
            return False

    def flush(self) -> None:
        """Flush buffer to storage. Default implementation clears buffer.

        Subclasses should override to perform batch inserts.
        """
        self._buffer.clear()

    def _upsert_atm_reference(
        self, atm_id: str, os_version: str = None, location_code: str = None
    ):
        """Buffer ATM reference data discovered dynamically in the logging streams."""
        cached = self._atm_ref_cache.setdefault(
            atm_id, {"os_version": None, "location_code": None}
        )

        needs_update = False
        if os_version and cached["os_version"] != os_version:
            cached["os_version"] = os_version
            needs_update = True
        if location_code and cached["location_code"] != location_code:
            cached["location_code"] = location_code
            needs_update = True

        if needs_update:
            self.ref_buffer.append((atm_id, os_version, location_code))
            if len(self.ref_buffer) >= self.batch_size:
                conn = None
                try:
                    from backend.src.database.connection import get_conn, release_conn

                    conn = get_conn()
                    self._flush_ref_buffer(conn)
                finally:
                    if conn:
                        try:
                            release_conn(conn)
                        except Exception:
                            pass

    def _flush_ref_buffer(self, conn) -> None:
        if not self.ref_buffer:
            return
        sql = """
            INSERT INTO atms (atm_id, os_version, location_code)
            VALUES %s
            ON CONFLICT (atm_id) DO UPDATE SET
                os_version = COALESCE(EXCLUDED.os_version, atms.os_version),
                location_code = COALESCE(EXCLUDED.location_code, atms.location_code)
        """
        try:
            from backend.src.ingestion.write_helper import write_batch

            write_batch(conn, sql, self.ref_buffer)
        except Exception:
            logger.exception("Failed to flush dynamic ATM reference updates")
        self.ref_buffer.clear()

    @classmethod
    def validate_sample(
        cls,
        file_path: str,
        db_path: Optional[str] = None,
        sample_lines: int = 10,
        max_fail_ratio: float = 0.3,
    ) -> bool:
        """
        Class-level sample validator that uses the parser's own `parse_line` logic.

        Returns True if the sample passes (failures within threshold), False otherwise.
        This method is intentionally lightweight and only samples the file; it
        does not record ingestion_errors (that is the parser's job during full ingestion).
        """
        try:
            parser = cls(db_path=db_path, batch_size=1)
        except Exception:
            return True

        fails = 0
        total = 0
        try:
            with open(file_path, "r", encoding="utf-8") as fh:
                # skip header if present
                fh.readline()
                for ln in fh:
                    if total >= sample_lines:
                        break
                    ln = ln.strip()
                    if not ln:
                        continue
                    total += 1
                    try:
                        parser.parse_line(ln)
                    except Exception:
                        fails += 1
        except Exception:
            return False

        if total == 0:
            return True
        fail_ratio = fails / total
        return fail_ratio <= max_fail_ratio

    def insert_ingestion_error(
        self, error_detail: str, raw_input: str, source: str = "UNKNOWN"
    ) -> None:
        """Write a row to `ingestion_errors` table, best-effort.

        This never raises; failures are logged only.
        """
        try:
            from backend.src.database.connection import get_conn, release_conn

            conn = get_conn()
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO ingestion_errors (timestamp, source, error_detail, raw_input) VALUES (%s, %s, %s, %s)",
                    (datetime.now(timezone.utc), source, error_detail, raw_input),
                )
            conn.commit()
        except Exception:
            logger.exception("Unable to write ingestion_errors row")
        finally:
            try:
                release_conn(conn)
            except Exception:
                pass


class EventDataParser(BaseParser):
    """Parser base for inserting into the `events` table.

    Expects buffered items to be dicts containing keys matching the events
    table columns: timestamp, source, atm_id, correlation_id, transaction_id,
    event_type, severity, message, payload
    """

    def flush(self) -> None:
        if not self._buffer:
            return
        try:
            from backend.src.database.connection import get_conn, release_conn
            from backend.src.ingestion.write_helper import write_batch

            conn = get_conn()
            sql = (
                "INSERT INTO events (timestamp, source, atm_id, correlation_id, transaction_id,"
                " event_type, severity, message, payload) VALUES %s"
            )
            params = [
                (
                    row.get("timestamp"),
                    row.get("source"),
                    row.get("atm_id"),
                    row.get("correlation_id"),
                    row.get("transaction_id"),
                    row.get("event_type"),
                    row.get("severity"),
                    row.get("message"),
                    row.get("payload"),
                )
                for row in self._buffer
            ]
            write_batch(conn, sql, params)
        except Exception:
            logger.exception("Failed to flush EventDataParser buffer")
            # On failure, write ingestion_errors for visibility
            for row in self._buffer:
                try:
                    self.insert_ingestion_error(
                        "flush_failed", str(row), source=row.get("source", "ATM_APP")
                    )
                except Exception:
                    logger.exception(
                        "Failed to write ingestion error during flush failure"
                    )
        finally:
            if "conn" in locals() and conn:
                self._flush_ref_buffer(conn)
                try:
                    release_conn(conn)
                except Exception:
                    pass
            self._buffer.clear()


class MetricDataParser(BaseParser):
    """Parser base for inserting into the `metrics` table.

    Expects buffered items to contain: timestamp, source, entity_id, metric_name,
    metric_value, payload
    """

    def flush(self) -> None:
        if not self._buffer:
            return
        try:
            from backend.src.database.connection import get_conn, release_conn
            from backend.src.ingestion.write_helper import write_batch

            conn = get_conn()
            sql = (
                "INSERT INTO metrics (timestamp, source, entity_id, metric_name, metric_value, payload)"
                " VALUES %s"
            )
            params = [
                (
                    row.get("timestamp"),
                    row.get("source"),
                    row.get("entity_id"),
                    row.get("metric_name"),
                    row.get("metric_value"),
                    row.get("payload"),
                )
                for row in self._buffer
            ]
            write_batch(conn, sql, params)
        except Exception:
            logger.exception("Failed to flush MetricDataParser buffer")
            for row in self._buffer:
                try:
                    self.insert_ingestion_error(
                        "metrics_flush_failed",
                        str(row),
                        source=row.get("source", "METRIC"),
                    )
                except Exception:
                    logger.exception(
                        "Failed to write ingestion error during metrics flush failure"
                    )
        finally:
            if "conn" in locals() and conn:
                self._flush_ref_buffer(conn)
                try:
                    release_conn(conn)
                except Exception:
                    pass
            self._buffer.clear()
