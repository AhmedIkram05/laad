"""OpenTelemetry observability bootstrap for LAAD services."""

from backend.src.observability.tracing import instrument_fastapi, setup_tracing

__all__ = ["instrument_fastapi", "setup_tracing"]
