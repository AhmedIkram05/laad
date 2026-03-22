"""ATM application log parser implementation.

Maps ATM application JSON events into the `events` table format.
"""
from __future__ import annotations

import json
from typing import Optional, Dict, Any
from .base_parser import EventDataParser
from backend.ingestion.utils import parse_to_utc_iso


class AtmAppParser(EventDataParser):
    """Parser for ATM Application JSON logs.

    parse_line accepts a JSON string representing a single event or a
    JSON object string and returns a mapping suitable for `EventDataParser`.
    """

    def parse_line(self, line: str) -> Optional[Dict[str, Any]]:
        payload_obj = None
        if not line:
            raise ValueError('empty line')
        # Accept either a JSON object or a line with trailing commas etc.
        try:
            payload_obj = json.loads(line)
        except Exception:
            # Try to be permissive: sometimes tests pass dicts via str()
            raise

        # Normalise timestamp
        ts = parse_to_utc_iso(payload_obj.get('timestamp'))
        if not ts:
            raise ValueError('invalid timestamp')

        # Core explicit columns for `events`
        row = {
            'timestamp': ts,
            'source': 'ATM_APP',
            'atm_id': payload_obj.get('atm_id'),
            'correlation_id': payload_obj.get('correlation_id'),
            'transaction_id': payload_obj.get('transaction_id'),
            'event_type': payload_obj.get('event_type'),
            'severity': payload_obj.get('log_level'),
            'message': payload_obj.get('message'),
        }

        # Build payload for remaining fields (exclude keys already mapped)
        excluded = set(row.keys()) | {'timestamp'}
        extras = {k: v for k, v in payload_obj.items() if k not in excluded}
        row['payload'] = json.dumps(extras)

        return row
