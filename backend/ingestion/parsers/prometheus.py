"""Prometheus CSV metrics parser.

Parses a single CSV line (matching Assets/Synthetic Data/prometheus_metrics.csv)
and returns a metric mapping for insertion into `metrics` table.
"""
from __future__ import annotations

import csv
from io import StringIO
import re
from typing import Optional, Dict, Any
from .base_parser import MetricDataParser
from backend.ingestion.utils import parse_to_utc_iso


PROMETHEUS_HEADERS = [
    'timestamp', 'metric_name', 'metric_type', 'metric_value', 'service_name',
    'pod_name', 'container_id', 'label_area', 'label_env', 'help_text'
]


class PrometheusParser(MetricDataParser):
    def parse_line(self, line: str) -> Optional[Dict[str, Any]]:
        if not line:
            raise ValueError('empty line')

        reader = csv.reader(StringIO(line))
        try:
            row = next(reader)
        except Exception:
            raise ValueError('invalid csv')

        # If header line, skip
        if row and row[0] == 'timestamp':
            raise ValueError('header')

        # Pad or trim
        if len(row) < len(PROMETHEUS_HEADERS):
            # allow partial rows but fail if essential missing
            raise ValueError('incomplete row')

        data = dict(zip(PROMETHEUS_HEADERS, row))

        ts = parse_to_utc_iso(data.get('timestamp'))
        if not ts:
            raise ValueError('invalid timestamp')

        raw_value = data.get('metric_value')

        def _parse_metric_value(raw: Optional[str]) -> float:
            if raw is None:
                raise ValueError('invalid metric_value')
            s = raw.strip()
            # Try direct parse first
            try:
                return float(s)
            except Exception:
                pass

            # Remove any characters that are not digits, signs, dot, comma or exponent
            cleaned = re.sub(r"[^0-9\-\.,eE+ ]", "", s)
            if cleaned == '':
                raise ValueError('invalid metric_value')

            # If comma present and no dot, treat comma as decimal separator
            if ',' in cleaned and '.' not in cleaned:
                cleaned2 = cleaned.replace(',', '.')
            else:
                # remove thousands separators
                cleaned2 = cleaned.replace(',', '')

            try:
                return float(cleaned2)
            except Exception:
                # As a last resort, extract first numeric substring
                m = re.search(r'[-+]?[0-9]*\.[0-9]+|[-+]?[0-9]+', s)
                if m:
                    return float(m.group(0))
                raise ValueError('invalid metric_value')

        metric_value = _parse_metric_value(raw_value)

        entity = data.get('pod_name') or data.get('container_id') or data.get('service_name')

        metric_name = data.get('metric_name')
        if not metric_name:
            raise ValueError('missing metric_name')

        payload = {k: v for k, v in data.items() if k not in ('timestamp', 'metric_name', 'metric_value')}

        return {
            'timestamp': ts,
            'source': 'PROMETHEUS',
            'entity_id': entity or 'unknown',
            'metric_name': metric_name,
            'metric_value': metric_value,
            'payload': __import__('json').dumps(payload),
        }
