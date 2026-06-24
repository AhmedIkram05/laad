"""Anomaly syncer - syncs detected anomalies from PostgreSQL to ChromaDB.

This module periodically queries the anomalies table and syncs all anomaly types
(A1-A7, UNKNOWN, NORMAL) to ChromaDB for RAG retrieval. This allows the RAG
diagnostic assistant to answer questions about any anomaly type across any ATM.

Previously this only synced UNKNOWN and NORMAL anomalies, which meant A1-A7
anomalies were invisible to the RAG — queries like "what are all the issues with
ATM 1" would miss most of the data.

The syncer:
- Runs on a configurable interval (default: 60 seconds)
- Queries all anomaly types not yet synced
- Formats each anomaly as a text chunk with ATM ID and details
- Upserts to ChromaDB with appropriate metadata (atm_id, severity, _anomaly_tag)

Usage:
    from backend.kafka.anomaly_syncer import AnomalySyncer
    syncer = AnomalySyncer()
    syncer.run()  # Run once
    # or
    syncer.start(interval=60)  # Run continuously
"""

from __future__ import annotations

import logging
import os

from backend.src.database.connection import get_cursor
from backend.kafka.chroma_buffer import ChromaBuffer

log = logging.getLogger(__name__)

CHROMA_HOST = os.getenv("CHROMA_HOST", "localhost")
CHROMA_PORT = int(os.getenv("CHROMA_PORT", "8001"))


class AnomalySyncer:
    """Syncs anomalies from PostgreSQL to ChromaDB."""

    def __init__(self):
        self._chroma_buffer = None
        self._synced_ids: set[int] = set()
        self._init_chroma()

    def _init_chroma(self) -> None:
        """Initialize ChromaDB connection."""
        try:
            self._chroma_buffer = ChromaBuffer()
            log.info("AnomalySyncer initialized")
        except Exception as e:
            log.warning("ChromaDB unavailable for anomaly syncer: %s", e)
            self._chroma_buffer = None

    def _get_unsynced_anomalies(self) -> list[dict]:
        """Query PostgreSQL for all anomalies not yet synced with ChromaDB."""
        query = """
            SELECT id, detected_at, anomaly_type, atm_id, severity, title, explanation
            FROM anomalies
            WHERE anomaly_type IS NOT NULL
        """
        params = []
        if self._synced_ids:
            query += " AND id NOT IN %s"
            params.append(tuple(self._synced_ids))
        query += " ORDER BY detected_at DESC LIMIT 100"

        try:
            with get_cursor(commit=True) as cur:
                cur.execute(query, tuple(params))
                rows = cur.fetchall()
                return [
                    {
                        "id": row["id"],
                        "detected_at": row["detected_at"],
                        "anomaly_type": row["anomaly_type"],
                        "atm_id": row["atm_id"],
                        "severity": row["severity"],
                        "title": row["title"],
                        "explanation": row["explanation"],
                    }
                    for row in rows
                ]
        except Exception as e:
            log.error("Failed to query anomalies: %s", e)
            return []

    def _format_anomaly_text(self, anomaly: dict) -> str:
        """Format anomaly as text for ChromaDB embedding."""
        parts = [
            f"[{anomaly['anomaly_type']}] {anomaly.get('title', 'Unknown anomaly')}",
            f"ATM: {anomaly['atm_id']}",
            f"Detected: {anomaly['detected_at'].isoformat() if anomaly.get('detected_at') else 'N/A'}",
        ]

        explanation = anomaly.get("explanation")
        if explanation:
            if isinstance(explanation, str):
                parts.append(f"Details: {explanation[:500]}")
            elif isinstance(explanation, dict):
                details = ", ".join(f"{k}={v}" for k, v in explanation.items() if v)
                parts.append(f"Details: {details[:500]}")

        return " | ".join(parts)

    def sync_once(self) -> dict:
        """Run a single sync cycle. Returns summary of synced anomalies."""
        if not self._chroma_buffer or not self._chroma_buffer._ready:
            return {"synced": 0, "status": "chroma_unavailable"}

        anomalies = self._get_unsynced_anomalies()
        if not anomalies:
            return {"synced": 0, "status": "no_new_anomalies"}

        synced_count = 0
        for anomaly in anomalies:
            try:
                text = self._format_anomaly_text(anomaly)
                timestamp = (
                    anomaly["detected_at"].isoformat()
                    if anomaly.get("detected_at")
                    else "2026-01-01T00:00:00+00:00"
                )
                severity = anomaly.get("severity", "INFO")
                anomaly_type = anomaly["anomaly_type"]

                self._chroma_buffer.add_event(
                    atm_id=anomaly["atm_id"],
                    text=text,
                    timestamp=timestamp,
                    severity=severity,
                    anomaly_tag=anomaly_type,
                )

                self._synced_ids.add(anomaly["id"])
                synced_count += 1

            except Exception as e:
                log.warning("Failed to sync anomaly %d: %s", anomaly["id"], e)

        if synced_count > 0:
            self._chroma_buffer.flush_all()
            log.info("Synced %d anomalies to ChromaDB", synced_count)

        return {"synced": synced_count, "status": "success"}

    def run(self, interval: int = 60) -> None:
        """Run the syncer continuously.

        Args:
            interval: Seconds between sync cycles (default: 60)
        """
        import time

        log.info("Starting anomaly syncer (interval=%ds)", interval)
        while True:
            try:
                result = self.sync_once()
                log.debug("Anomaly syncer result: %s", result)
            except Exception as e:
                log.error("Anomaly syncer error: %s", e)
            time.sleep(interval)


def run_syncer(interval: int = 60) -> None:
    """Entry point for running the anomaly syncer as a standalone process."""
    syncer = AnomalySyncer()
    syncer.run(interval)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Sync anomalies to ChromaDB")
    parser.add_argument(
        "--interval", type=int, default=60, help="Sync interval in seconds"
    )
    args = parser.parse_args()
    run_syncer(args.interval)
