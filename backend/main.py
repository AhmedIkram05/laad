#!/usr/bin/env python3
"""Orchestrator: init DB, generate custom dataset, and ingest all sources.

Run using:
    python3 main.py

"""
from __future__ import annotations

# When executed directly from the `backend/` folder (python3 main.py), the
# package root isn't on `sys.path` so absolute imports like `backend.*`
# fail. Ensure the project root is available when running as a script.
if __package__ is None:
    import sys
    from pathlib import Path

    repo_root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(repo_root))

import argparse
import os
import subprocess
import sqlite3
import sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict


def init_db(db_path: str):
    import backend.src.database.init_db as init_db_mod

    print("Initialising database (schema + seeds)...")
    init_db_mod.init_db()


def run_generator(output: str) -> None:
    """Run the project generator. Always regenerates to ensure freshness."""
    import backend.src.ingestion.custom_data_generator as gen
    gen.generate_dataset(output=output)


def ingest_file(db_path: str, parser_cls, file_path: str, source: str, kind: str = "json"):
    print(f"Ingesting {file_path} -> {source} ({kind})")
    parser = parser_cls(db_path=db_path, batch_size=200)
    if kind == "json":
        import json

        with open(file_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        for item in data:
            parser.process_line(json.dumps(item), source=source)
    else:
        with open(file_path, "r", encoding="utf-8") as fh:
            header = fh.readline()
            for ln in fh:
                ln = ln.strip()
                if not ln:
                    continue
                parser.process_line(ln, source=source)
    parser.flush()
    print(f"Finished ingesting {file_path}")

def validate_file_sample(file_path: str, parser_cls, db_path: str, sample_lines: int = 10, max_fail_ratio: float = 0.3) -> bool:
    """Delegate sample validation to the parser class.

    This offloads line-level validation to the parser implementation so
    parsing logic remains authoritative and sample-checks reuse the same
    semantics.
    """
    try:
        return parser_cls.validate_sample(file_path, db_path=db_path, sample_lines=sample_lines, max_fail_ratio=max_fail_ratio)
    except Exception:
        return False

def final_counts(db_path: str):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    def one(q):
        try:
            cur.execute(q)
            return cur.fetchone()[0]
        except Exception:
            return None
    events = one("SELECT COUNT(*) FROM events")
    metrics = one("SELECT COUNT(*) FROM metrics")
    errors = one("SELECT COUNT(*) FROM ingestion_errors")
    # Force WAL checkpoint to merge -wal and -shm files back into database.db
    # TRUNCATE mode also attempts to delete the -wal and -shm files on success.
    try:
        cur.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    except Exception:
        pass
    conn.close()
    print("\n=== DB Summary ===")
    print(f"events: {events}")
    print(f"metrics: {metrics}")
    print(f"ingestion_errors: {errors}")


def run_pipeline(
    db_path: str = "database/database.db",
    output: str = "custom_synthetic_data_sources",
    workers: int = 4,
) -> None:
    """End-to-end programmatic pipeline execution."""
    # Phase 1: DB init
    init_db(db_path)
    # Phase 2: data generation (generator has its own defaults)
    run_generator(output)

    # Phase 3: ingestion
    # Map generated files -> parser classes
    from backend.src.ingestion.parsers.atm_app import AtmAppParser
    from backend.src.ingestion.parsers.hardware_sensor import HardwareSensorParser
    from backend.src.ingestion.parsers.terminal_handler import TerminalHandlerParser
    from backend.src.ingestion.parsers.kafka_metrics import KafkaMetricsParser
    from backend.src.ingestion.parsers.prometheus import PrometheusParser
    from backend.src.ingestion.parsers.windows_os import WindowsOSParser
    from backend.src.ingestion.parsers.gcp_cloud_metrics import GcpCloudMetricsParser

    registry = [
        ("atm_application_log.json", AtmAppParser, "ATM_APP", "json"),
        ("atm_hardware_sensor_log.json", HardwareSensorParser, "HARDWARE", "json"),
        ("terminal_handler_app_log.json", TerminalHandlerParser, "TERMINAL_HANDLER", "json"),
        ("kafka_atm_metrics_stream.json", KafkaMetricsParser, "KAFKA", "json"),
        ("prometheus_metrics.csv", PrometheusParser, "PROMETHEUS", "csv"),
        ("windows_os_metrics.csv", WindowsOSParser, "OS", "csv"),
        ("gcp_cloud_metrics.csv", GcpCloudMetricsParser, "CLOUD", "csv"),
    ]

    files_dir = output
    tasks = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {}
        for fname, parser_cls, source, kind in registry:
            path = os.path.join(files_dir, fname)
            if not os.path.exists(path):
                print(f"Warning: expected file not found: {path}; skipping")
                continue
            # validate small sample before submitting to ingestion
            if kind == "csv" or fname.endswith(".csv"):
                ok = validate_file_sample(path, parser_cls, db_path)
                if not ok:
                    print(f"Skipping ingestion for {path} due to validation failures.")
                    continue

            fut = ex.submit(ingest_file, db_path, parser_cls, path, source, kind)
            futures[fut] = path

        for fut in as_completed(futures):
            path = futures[fut]
            try:
                fut.result()
            except Exception as e:
                print(f"Ingestion worker failed for {path}: {e}")

    # Final counts
    final_counts(db_path)


OUTPUT_DIR = Path("custom_synthetic_data_sources")
DB_PATH = str(OUTPUT_DIR.joinpath("database", "database.db"))


def main():
    """Main entry point using hardcoded configuration for simplicity."""
    # Call the simplified pipeline: DB init -> generator (module defaults) -> ingest
    run_pipeline(db_path=DB_PATH, output=OUTPUT_DIR)


if __name__ == "__main__":
    main()
