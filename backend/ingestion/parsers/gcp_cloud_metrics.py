"""GCP cloud metrics CSV parser.

Parses `gcp_cloud_metrics.csv` rows and maps into `metrics` table.
Uses `metric_name` and `metric_value` columns when present.
"""
from __future__ import annotations

import csv
from io import StringIO
from typing import Optional, Dict, Any
from .base_parser import MetricDataParser
from backend.ingestion.utils import parse_to_utc_iso


GCP_HEADERS = [
    'timestamp','project_id','resource_type','resource_id','zone','metric_name','metric_value',
    'metric_unit','cpu_usage_percent','memory_usage_bytes','memory_limit_bytes','network_ingress_bytes',
    'network_egress_bytes','restart_count','label_app','label_env','label_version'
]


class GcpCloudMetricsParser(MetricDataParser):
    def parse_line(self, line: str) -> Optional[Dict[str, Any]]:
        if not line:
            raise ValueError('empty line')
        reader = csv.reader(StringIO(line))
        try:
            row = next(reader)
        except Exception:
            raise ValueError('invalid csv')

        if row and row[0] == 'timestamp':
            raise ValueError('header')

        if len(row) < len(GCP_HEADERS):
            # allow rows missing optional trailing fields
            # but ensure minimum columns exist
            if len(row) < 7:
                raise ValueError('incomplete row')

        # zip stops at shortest; that's fine
        data = dict(zip(GCP_HEADERS, row))

        ts = parse_to_utc_iso(data.get('timestamp'))
        if not ts:
            raise ValueError('invalid timestamp')

        metric_name = data.get('metric_name') or ('cpu_usage_percent' if data.get('cpu_usage_percent') else None)
        metric_value_raw = data.get('metric_value') or data.get('cpu_usage_percent')
        if metric_value_raw is None or metric_name is None:
            raise ValueError('no metric value present')

        try:
            metric_value = float(metric_value_raw)
        except Exception:
            raise ValueError('invalid metric_value')

        entity = data.get('resource_id') or data.get('project_id')

        payload = {k: v for k, v in data.items() if k not in ('timestamp', 'metric_name', 'metric_value')}

        return {
            'timestamp': ts,
            'source': 'CLOUD',
            'entity_id': entity or 'unknown',
            'metric_name': metric_name,
            'metric_value': metric_value,
            'payload': __import__('json').dumps(payload),
        }
