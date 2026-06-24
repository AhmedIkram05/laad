"""Edge case tests for all 8 parsers.

Covers 3 categories per parser: malformed input, missing required fields,
and boundary/incomplete values. Uses parametrize for compact coverage.
"""

import pytest

from backend.src.ingestion.parsers.atm_app import AtmAppParser
from backend.src.ingestion.parsers.base_parser import BaseParser
from backend.src.ingestion.parsers.gcp_cloud_metrics import GcpCloudMetricsParser
from backend.src.ingestion.parsers.hardware_sensor import HardwareSensorParser
from backend.src.ingestion.parsers.kafka_metrics import KafkaMetricsParser
from backend.src.ingestion.parsers.prometheus import PrometheusParser
from backend.src.ingestion.parsers.terminal_handler import TerminalHandlerParser
from backend.src.ingestion.parsers.windows_os import WindowsOSParser


class DummyParser(BaseParser):
    """Minimal BaseParser subclass for testing base error handling."""
    def parse_line(self, line: str):
        line = line.strip()
        if line == "BAD":
            raise ValueError("malformed")
        return {"raw": line}


# ── Edge cases: process_line should return False for invalid inputs ──────
# Each tuple: (parser_class, bad_input)
# Covers: malformed, missing required fields, boundary/incomplete

EDGE_CASES_PROCESS_LINE = [
    # === JSON event parsers ===
    # AtmAppParser
    (AtmAppParser, ""),
    (AtmAppParser, "{invalid json"),
    (AtmAppParser, '{"not_a_timestamp": true}'),
    # HardwareSensorParser
    (HardwareSensorParser, ""),
    (HardwareSensorParser, "{not valid}"),
    (HardwareSensorParser, '{"no_timestamp": 1}'),
    # TerminalHandlerParser
    (TerminalHandlerParser, ""),
    (TerminalHandlerParser, "{garbage}"),
    (TerminalHandlerParser, '{"missing_ts": "yes"}'),
    # === JSON metric parsers ===
    # KafkaMetricsParser
    (KafkaMetricsParser, ""),
    (KafkaMetricsParser, "{bad"),
    (KafkaMetricsParser, '{"timestamp": "2026-01-01T00:00:00Z"}'),
    # KafkaMetricsParser — present but no entity_id
    (KafkaMetricsParser, '{"timestamp": "2026-01-01T00:00:00Z", "transaction_rate_tps": 10}'),
    # === CSV metric parsers ===
    # GcpCloudMetricsParser
    (GcpCloudMetricsParser, ""),
    (GcpCloudMetricsParser, "timestamp,project_id,metric_name"),
    (GcpCloudMetricsParser, "2026-01-01T00:00:00Z,proj1"),
    # PrometheusParser
    (PrometheusParser, ""),
    (PrometheusParser, "timestamp,metric_name"),
    (PrometheusParser, "2026-01-01T00:00:00Z,my_metric"),
    # WindowsOSParser
    (WindowsOSParser, ""),
    (WindowsOSParser, "timestamp,atm_id"),
    (WindowsOSParser, "2026-01-01T00:00:00Z,ATM-1"),
    # === BaseParser subclass ===
    (DummyParser, "BAD"),
    (DummyParser, " BAD "),   # whitespace-trimmed to "BAD"
    (DummyParser, "BAD\n"),   # stripped to "BAD"
]


class TestParsersProcessLineEdgeCases:
    """Verify process_line returns False for all edge case inputs."""

    @pytest.mark.parametrize("parser_cls, bad_input", EDGE_CASES_PROCESS_LINE)
    def test_process_line_returns_false_on_invalid_input(self, parser_cls, bad_input):
        parser = parser_cls(batch_size=1)
        result = parser.process_line(bad_input)
        assert result is False, (
            f"{parser_cls.__name__}.process_line({bad_input!r}) "
            f"expected False, got {result}"
        )


# ── Edge cases: parse_line should raise ValueError on invalid inputs ─────
# Some parsers need the raw exception raised by parse_line (not wrapped by
# process_line) for direct testing of validation logic.
# Note: DummyParser's "BAD" already covered above via process_line;
# for empty lines, the JSON parsers raise, but DummyParser does not.

EDGE_CASES_PARSE_LINE = [
    # CSV header lines raise ValueError("header") rather than inserting
    (GcpCloudMetricsParser, "timestamp,project_id,resource_type,resource_id,zone,metric_name,metric_value", "header"),
    (PrometheusParser, "timestamp,metric_name,metric_type,metric_value,service_name", "header"),
    (WindowsOSParser, "timestamp,atm_id,hostname,os_version,cpu_usage_percent", "header"),
    # Incomplete CSV rows (too few columns)
    (GcpCloudMetricsParser, "2026-01-01T00:00:00Z", "incomplete row"),
    # Non-numeric metric value in CSV
    (GcpCloudMetricsParser, "2026-01-01T00:00:00Z,proj1,type,res1,zone1,cpu_usage,not_a_number,,1,,,,,,,", "invalid metric_value"),
]


class TestParsersParseLineEdgeCases:
    """Verify parse_line raises ValueError on specific edge cases."""

    @pytest.mark.parametrize("parser_cls, bad_input, expected_match", EDGE_CASES_PARSE_LINE)
    def test_parse_line_raises_value_error(self, parser_cls, bad_input, expected_match):
        parser = parser_cls(batch_size=1)
        with pytest.raises(ValueError, match=expected_match):
            parser.parse_line(bad_input)


# ── DummyParser-specific process_line behavior ───────────────────────────

class TestDummyParserEdgeCases:
    """Additional edge cases for BaseParser subclasses via DummyParser."""

    def test_good_line_returns_true(self):
        parser = DummyParser(batch_size=1)
        assert parser.process_line("good data") is True

    def test_empty_line_via_process_line_returns_true(self):
        """Empty line is not 'BAD', so DummyParser accepts it."""
        parser = DummyParser(batch_size=1)
        assert parser.process_line("") is True
