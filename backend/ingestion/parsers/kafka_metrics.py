"""Kafka ATM metrics parser.

Maps Kafka ATM metric messages into the `metrics` table. Uses
`transaction_rate_tps` as the primary metric and includes the rest
of the fields in `payload` for now.
"""
from __future__ import annotations

import json
from typing import Optional, Dict, Any
from .base_parser import MetricDataParser
from backend.ingestion.utils import parse_to_utc_iso


class KafkaMetricsParser(MetricDataParser):
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

        # Choose a representative metric for quick ingestion. Use transaction_rate_tps
        metric_name = 'transaction_rate_tps'
        metric_value = obj.get('transaction_rate_tps')
        if metric_value is None:
            # If primary metric missing, fallback to response_time_ms
            metric_name = 'response_time_ms'
            metric_value = obj.get('response_time_ms')

        if metric_value is None:
            raise ValueError('no metric value present')

        entity_id = obj.get('atm_id') or obj.get('entity_id')
        if not entity_id:
            raise ValueError('missing entity_id')

        row = {
            'timestamp': ts,
            'source': 'KAFKA',
            'entity_id': entity_id,
            'metric_name': metric_name,
            'metric_value': float(metric_value),
            'payload': json.dumps({k: v for k, v in obj.items() if k not in ('timestamp', 'atm_id', 'transaction_rate_tps', 'response_time_ms')})
        }

        return row
