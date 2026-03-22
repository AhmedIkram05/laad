"""Base ingestor/parser utilities.

Provides a resilient BaseParser class that catches parsing errors and
records bad inputs to the `ingestion_errors` table. Designed to be
subclassed for source-specific parsers.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone
import os
import sqlite3
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class BaseParser(ABC):
    """Abstract base parser for ingestion.

    Subclasses implement `parse_line` which should either return a
    dictionary representing the parsed row (for buffering/insertion)
    or raise an exception for malformed input.
    """

    def __init__(self, db_path: Optional[str] = None, batch_size: int = 500):
        self.db_path = db_path or os.getenv('DB_PATH', 'database/database.db')
        self.batch_size = int(batch_size)
        self._buffer: list[Dict[str, Any]] = []

    @abstractmethod
    def parse_line(self, line: str) -> Optional[Dict[str, Any]]:
        """Parse a single input line and return a mapping or raise on error."""

    def process_line(self, line: str, source: str = 'UNKNOWN') -> bool:
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

    def insert_ingestion_error(self, error_detail: str, raw_input: str, source: str = 'UNKNOWN') -> None:
        """Write a row to `ingestion_errors` table, best-effort.

        This never raises; failures are logged only.
        """
        try:
            from backend.database.connection import get_db

            conn = get_db(self.db_path)
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO ingestion_errors (timestamp, source, error_detail, raw_input) VALUES (?, ?, ?, ?)",
                (datetime.now(timezone.utc).isoformat(), source, error_detail, raw_input),
            )
            conn.commit()
        except Exception:
            logger.exception("Unable to write ingestion_errors row")
        finally:
            try:
                conn.close()
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
            from backend.database.connection import get_db
            from backend.ingestion.write_helper import write_batch

            conn = get_db(self.db_path)
            sql = (
                "INSERT INTO events (timestamp, source, atm_id, correlation_id, transaction_id,"
                " event_type, severity, message, payload) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
            )
            params = [(
                row.get('timestamp'),
                row.get('source'),
                row.get('atm_id'),
                row.get('correlation_id'),
                row.get('transaction_id'),
                row.get('event_type'),
                row.get('severity'),
                row.get('message'),
                row.get('payload'),
            ) for row in self._buffer]
            write_batch(conn, sql, params)
        except Exception:
            logger.exception("Failed to flush EventDataParser buffer")
            # On failure, write ingestion_errors for visibility
            for row in self._buffer:
                try:
                    self.insert_ingestion_error('flush_failed', str(row), source=row.get('source', 'ATM_APP'))
                except Exception:
                    logger.exception("Failed to write ingestion error during flush failure")
        finally:
            try:
                conn.close()
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
            from backend.database.connection import get_db
            from backend.ingestion.write_helper import write_batch

            conn = get_db(self.db_path)
            sql = (
                "INSERT INTO metrics (timestamp, source, entity_id, metric_name, metric_value, payload)"
                " VALUES (?, ?, ?, ?, ?, ?)"
            )
            params = [(
                row.get('timestamp'),
                row.get('source'),
                row.get('entity_id'),
                row.get('metric_name'),
                row.get('metric_value'),
                row.get('payload'),
            ) for row in self._buffer]
            write_batch(conn, sql, params)
        except Exception:
            logger.exception("Failed to flush MetricDataParser buffer")
            for row in self._buffer:
                try:
                    self.insert_ingestion_error('metrics_flush_failed', str(row), source=row.get('source', 'METRIC'))
                except Exception:
                    logger.exception("Failed to write ingestion error during metrics flush failure")
        finally:
            try:
                conn.close()
            except Exception:
                pass
            self._buffer.clear()

    def insert_ingestion_error(self, error_detail: str, raw_input: str, source: str = 'UNKNOWN') -> None:
        """Write a row to `ingestion_errors` table, best-effort.

        This never raises; failures are logged only.
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO ingestion_errors (timestamp, source, error_detail, raw_input) VALUES (?, ?, ?, ?)",
                (datetime.now(timezone.utc).isoformat(), source, error_detail, raw_input),
            )
            conn.commit()
        except Exception:
            logger.exception("Unable to write ingestion_errors row")
        finally:
            try:
                conn.close()
            except Exception:
                pass
