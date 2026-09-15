"""Remaining-branch coverage for prometheus / windows_os / gcp / kafka parsers.

Uses parse_line directly (no DB). Covers invalid-csv, timestamp,
metric-value cleaning, entity fallbacks and metric fallbacks.
"""

from __future__ import annotations

import csv
import json
from unittest.mock import patch

import pytest

from backend.src.ingestion.parsers.gcp_cloud_metrics import GcpCloudMetricsParser
from backend.src.ingestion.parsers.kafka_metrics import KafkaMetricsParser
from backend.src.ingestion.parsers.prometheus import PrometheusParser
from backend.src.ingestion.parsers.windows_os import WindowsOSParser

TS = "2026-03-05T09:15:00Z"


def _prom_line(metric_value="12.5", metric_name="my_metric", ts=TS, extra=None):
    # timestamp,metric_name,metric_type,metric_value,service,pod,container,area,env,help
    parts = [ts, metric_name, "gauge", metric_value, "svc", "pod-1", "cid-1", "area", "prod", "help"]
    if extra:
        parts.extend(extra)
    # quote fields containing commas
    out = []
    for p in parts:
        out.append(f'"{p}"' if "," in p else p)
    return ",".join(out)


def _win_line(cpu="42.5", ts=TS, atm="ATM-GB-0001", osv="10.0.1"):
    # 17 cols per WINDOWS_HEADERS
    row = [ts, atm, "host1", osv, cpu, "4000", "8000", "50",
           "100", "200", "99", "10", "20", "0", "80", "12345", "0"]
    return ",".join(row)


def _gcp_line(metric_name="cpu_usage", metric_value="3.25", ts=TS, resource="res-1", project="proj-1"):
    row = [ts, project, "gke_container", resource, "zone-a", metric_name,
           metric_value, "units", "10", "100", "200", "1", "2", "0",
           "app", "prod", "v1"]
    return ",".join(row)


class TestPrometheusRemaining:
    def test_invalid_csv_raises(self):
        p = PrometheusParser()
        with patch.object(csv, "reader", return_value=iter([])):
            with pytest.raises(ValueError, match="invalid csv"):
                p.parse_line("anything")

    def test_invalid_timestamp(self):
        p = PrometheusParser()
        with pytest.raises(ValueError, match="invalid timestamp"):
            p.parse_line(_prom_line(ts="not-a-date"))

    def test_missing_metric_name(self):
        p = PrometheusParser()
        with pytest.raises(ValueError, match="missing metric_name"):
            p.parse_line(_prom_line(metric_name=""))

    def test_empty_metric_value(self):
        p = PrometheusParser()
        with pytest.raises(ValueError, match="invalid metric_value"):
            p.parse_line(_prom_line(metric_value=""))

    def test_symbols_only_metric_value(self):
        p = PrometheusParser()
        with pytest.raises(ValueError, match="invalid metric_value"):
            p.parse_line(_prom_line(metric_value="!!!"))

    def test_comma_decimal_separator(self):
        p = PrometheusParser()
        out = p.parse_line(_prom_line(metric_value="1,5"))
        assert out["metric_value"] == pytest.approx(1.5)

    def test_thousands_separator(self):
        p = PrometheusParser()
        out = p.parse_line(_prom_line(metric_value="1,234.56"))
        assert out["metric_value"] == pytest.approx(1234.56)

    def test_currency_symbols_cleaned(self):
        p = PrometheusParser()
        out = p.parse_line(_prom_line(metric_value="$123.45!"))
        assert out["metric_value"] == pytest.approx(123.45)

    def test_double_dot_falls_back_to_first_number(self):
        p = PrometheusParser()
        out = p.parse_line(_prom_line(metric_value="1.2.3"))
        assert out["metric_value"] == pytest.approx(1.2)

    def test_letters_rejected(self):
        p = PrometheusParser()
        with pytest.raises(ValueError, match="invalid metric_value"):
            p.parse_line(_prom_line(metric_value="12abc"))

    def test_no_numeric_substring_rejected(self):
        p = PrometheusParser()
        with pytest.raises(ValueError, match="invalid metric_value"):
            p.parse_line(_prom_line(metric_value="--"))

    def test_entity_fallback_service(self):
        p = PrometheusParser()
        # empty pod + container -> service_name used
        line = ",".join([TS, "m", "gauge", "1.0", "svc-9", "", "", "a", "prod", "h"])
        out = p.parse_line(line)
        assert out["entity_id"] == "svc-9"

    def test_entity_unknown(self):
        p = PrometheusParser()
        line = ",".join([TS, "m", "gauge", "1.0", "", "", "", "a", "prod", "h"])
        out = p.parse_line(line)
        assert out["entity_id"] == "unknown"

    def test_extra_columns_trimmed(self):
        p = PrometheusParser()
        out = p.parse_line(_prom_line(extra=["zzz", "yyy"]))
        assert out["metric_name"] == "my_metric"


class TestWindowsRemaining:
    def test_invalid_csv(self):
        p = WindowsOSParser()
        with patch.object(csv, "reader", return_value=iter([])):
            with pytest.raises(ValueError, match="invalid csv"):
                p.parse_line("x")

    def test_invalid_timestamp(self):
        p = WindowsOSParser()
        with pytest.raises(ValueError, match="invalid timestamp"):
            p.parse_line(_win_line(ts="garbage"))

    def test_invalid_metric_value(self):
        p = WindowsOSParser()
        with pytest.raises(ValueError, match="invalid metric_value"):
            p.parse_line(_win_line(cpu="not-a-float"))

    def test_empty_metric_value(self):
        p = WindowsOSParser()
        with pytest.raises(ValueError, match="invalid metric_value"):
            p.parse_line(_win_line(cpu=""))

    def test_unknown_entity(self):
        p = WindowsOSParser()
        out = p.parse_line(_win_line(atm=""))
        assert out["entity_id"] == "unknown"
        assert out["metric_name"] == "cpu_usage_percent"

    def test_no_os_upsert_when_missing(self):
        p = WindowsOSParser()
        with patch.object(p, "_upsert_atm_reference") as mock_up:
            p.parse_line(_win_line(osv=""))
            mock_up.assert_not_called()

    def test_os_upsert_called(self):
        p = WindowsOSParser()
        with patch.object(p, "_upsert_atm_reference") as mock_up:
            p.parse_line(_win_line())
            mock_up.assert_called_once_with("ATM-GB-0001", os_version="10.0.1")


class TestGcpRemaining:
    def test_invalid_csv(self):
        p = GcpCloudMetricsParser()
        with patch.object(csv, "reader", return_value=iter([])):
            with pytest.raises(ValueError, match="invalid csv"):
                p.parse_line("x")

    def test_invalid_timestamp(self):
        p = GcpCloudMetricsParser()
        with pytest.raises(ValueError, match="invalid timestamp"):
            p.parse_line(_gcp_line(ts="bad-ts"))

    def test_no_metric_value(self):
        p = GcpCloudMetricsParser()
        # both metric_value and cpu_usage_percent empty
        row = [TS, "proj-1", "t", "res-1", "z", "", "", "u", "", "", "", "", "", "", "", "", ""]
        with pytest.raises(ValueError, match="no metric value"):
            p.parse_line(",".join(row))

    def test_metric_name_fallback_to_cpu(self):
        p = GcpCloudMetricsParser()
        row = [TS, "proj-1", "t", "res-1", "z", "", "7.5", "u", "9.5", "", "", "", "", "", "", "", ""]
        # metric_name empty but cpu_usage_percent present -> metric_value from metric_value col,
        # name falls back to cpu_usage_percent... here metric_value present ("7.5") so name None?
        # Build row where metric_name empty and metric_value empty but cpu present:
        row2 = [TS, "proj-1", "t", "res-1", "z", "", "", "u", "9.5", "", "", "", "", "", "", "", ""]
        out = p.parse_line(",".join(row2))
        assert out["metric_name"] == "cpu_usage_percent"
        assert out["metric_value"] == pytest.approx(9.5)

    def test_invalid_metric_value(self):
        p = GcpCloudMetricsParser()
        with pytest.raises(ValueError, match="invalid metric_value"):
            p.parse_line(_gcp_line(metric_value="NaN-ish-xyz"))

    def test_entity_fallback_project(self):
        p = GcpCloudMetricsParser()
        out = p.parse_line(_gcp_line(resource=""))
        assert out["entity_id"] == "proj-1"

    def test_entity_unknown(self):
        p = GcpCloudMetricsParser()
        row = [TS, "", "t", "", "z", "m", "1.0", "u", "", "", "", "", "", "", "", "", ""]
        out = p.parse_line(",".join(row))
        assert out["entity_id"] == "unknown"

    def test_short_row_with_minimum_cols(self):
        p = GcpCloudMetricsParser()
        # 7 cols minimum: ts, project, type, resource, zone, name, value
        out = p.parse_line(f"{TS},proj-1,t,res-7,zone-x,my_metric,2.5")
        assert out["metric_value"] == pytest.approx(2.5)
        assert out["entity_id"] == "res-7"


class TestKafkaRemaining:
    def test_invalid_timestamp(self):
        p = KafkaMetricsParser()
        line = json.dumps({"timestamp": "bad", "transaction_rate_tps": 5, "atm_id": "A1"})
        with pytest.raises(ValueError, match="invalid timestamp"):
            p.parse_line(line)

    def test_missing_timestamp(self):
        p = KafkaMetricsParser()
        line = json.dumps({"transaction_rate_tps": 5, "atm_id": "A1"})
        with pytest.raises(ValueError, match="invalid timestamp"):
            p.parse_line(line)

    def test_fallback_to_response_time(self):
        p = KafkaMetricsParser()
        line = json.dumps({"timestamp": TS, "response_time_ms": 123.0, "atm_id": "ATM-1"})
        out = p.parse_line(line)
        assert out["metric_name"] == "response_time_ms"
        assert out["metric_value"] == pytest.approx(123.0)

    def test_entity_id_alias(self):
        p = KafkaMetricsParser()
        line = json.dumps({"timestamp": TS, "transaction_rate_tps": 9, "entity_id": "E-9"})
        out = p.parse_line(line)
        assert out["entity_id"] == "E-9"

    def test_payload_excludes_timestamp_and_atm(self):
        p = KafkaMetricsParser()
        line = json.dumps({"timestamp": TS, "transaction_rate_tps": 9, "atm_id": "A1", "extra": "x"})
        out = p.parse_line(line)
        payload = json.loads(out["payload"])
        assert "timestamp" not in payload
        assert "atm_id" not in payload
        assert payload["extra"] == "x"
