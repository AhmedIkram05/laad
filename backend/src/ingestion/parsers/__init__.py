"""Ingestion parsers package.

Exports base parser classes for event and metric data parsing.
"""

from .base_parser import BaseParser, EventDataParser, MetricDataParser

__all__ = ["BaseParser", "EventDataParser", "MetricDataParser"]
