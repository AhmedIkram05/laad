"""Windows OS CSV metrics parser.

Parses rows from `windows_os_metrics.csv`. Chooses `cpu_usage_percent`
as the primary metric for insertion; other fields are retained in payload.
"""

from __future__ import annotations

import csv
from io import StringIO
from typing import Optional, Dict, Any
from .base_parser import MetricDataParser
from ..utils import parse_to_utc_iso


WINDOWS_HEADERS = [
    "timestamp",
    "atm_id",
    "hostname",
    "os_version",
    "cpu_usage_percent",
    "memory_used_mb",
    "memory_total_mb",
    "memory_usage_percent",
    "disk_read_bytes_per_sec",
    "disk_write_bytes_per_sec",
    "disk_free_gb",
    "network_bytes_sent_per_sec",
    "network_bytes_recv_per_sec",
    "network_errors",
    "process_count",
    "system_uptime_seconds",
    "event_log_errors_last_min",
]


class WindowsOSParser(MetricDataParser):
    def parse_line(self, line: str) -> Optional[Dict[str, Any]]:
        if not line:
            raise ValueError("empty line")
        reader = csv.reader(StringIO(line))
        try:
            row = next(reader)
        except Exception:
            raise ValueError("invalid csv")

        if row and row[0] == "timestamp":
            raise ValueError("header")

        if len(row) < len(WINDOWS_HEADERS):
            raise ValueError("incomplete row")

        data = dict(zip(WINDOWS_HEADERS, row))

        ts = parse_to_utc_iso(data.get("timestamp"))
        if not ts:
            raise ValueError("invalid timestamp")

        try:
            metric_value = float(data.get("cpu_usage_percent"))
        except Exception:
            raise ValueError("invalid metric_value")

        entity = data.get("atm_id")

        # Dynamically upsert the ATM OS version if seen in the stream
        os_version = data.get("os_version")
        if entity and os_version:
            self._upsert_atm_reference(entity, os_version=os_version)

        payload = {
            k: v for k, v in data.items() if k not in ("timestamp", "cpu_usage_percent")
        }

        return {
            "timestamp": ts,
            "source": "OS",
            "entity_id": entity or "unknown",
            "metric_name": "cpu_usage_percent",
            "metric_value": metric_value,
            "payload": __import__("json").dumps(payload),
        }
