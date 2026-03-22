"""ATM hardware sensor log parser.

For now maps hardware sensor JSON into the `events` table. If a
`metric_name` and `metric_value` are present they are included in the
payload; future iteration may route such rows into `metrics`.
"""
from __future__ import annotations

import json
from typing import Optional, Dict, Any
from .base_parser import EventDataParser
from backend.ingestion.utils import parse_to_utc_iso


class HardwareSensorParser(EventDataParser):
    def parse_line(self, line: str) -> Optional[Dict[str, Any]]:
        if not line:
            raise ValueError('empty line')
        try:
            obj = json.loads(line)
        except Exception:
            raise

        ts = parse_to_utc_iso(obj.get('timestamp'))
        if not ts:
            raise ValueError('invalid timestamp')

        row = {
            'timestamp': ts,
            'source': 'HARDWARE',
            'atm_id': obj.get('atm_id'),
            'correlation_id': obj.get('correlation_id'),
            'transaction_id': obj.get('transaction_id'),
            'event_type': obj.get('event_type'),
            'severity': obj.get('severity'),
            'message': obj.get('message'),
        }

        excluded = set(row.keys()) | {'timestamp'}
        extras = {k: v for k, v in obj.items() if k not in excluded}
        row['payload'] = json.dumps(extras)
        return row
