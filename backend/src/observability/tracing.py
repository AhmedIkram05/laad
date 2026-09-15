"""OpenTelemetry tracing bootstrap for LAAD services.

The SDK is always installed (parent-based always-on sampling); the exporter
chain is decided by the environment only:

- ``OTEL_EXPORTER_OTLP_ENDPOINT`` set -> OTLP/gRPC span exporter to that
  endpoint (docker-compose points this at the collector, see docs/adr/0001).
- unset -> no exporter: spans are discarded locally so pytest sessions stay
  silent.

Application containers only ever know OTLP env vars; the full exporter chain
lives in docker-compose.
"""

from __future__ import annotations

import logging
import os

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.psycopg2 import Psycopg2Instrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

# Probe routes are pure noise: /health and /health/ready.
_EXCLUDED_URLS = "health,readiness"

_configured = False


class TraceContextLogFilter(logging.Filter):
    """Append ``trace_id=<hex> span_id=<hex>`` of the current span to a record.

    Dashes when no span is active. Attached at handler level so it also fires
    for records propagated up to the root logger; safe if applied twice.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if getattr(record, "trace_context_added", False):
            return True
        record.trace_context_added = True

        span_ctx = trace.get_current_span().get_span_context()
        if span_ctx.is_valid:
            body = (
                f"{record.getMessage()} "
                f"trace_id={span_ctx.trace_id:032x} span_id={span_ctx.span_id:016x}"
            )
        else:
            body = f"{record.getMessage()} trace_id=- span_id=-"
        record.msg = body
        record.args = None
        return True


def instrument_fastapi(app) -> None:
    """Instrument a FastAPI app after construction. Safe to call twice."""
    FastAPIInstrumentor.instrument_app(app, excluded_urls=_EXCLUDED_URLS)


def setup_tracing(service_name: str, log_filter: bool = True) -> None:
    """Bootstrap tracing once: SDK + env-decided exporter + instrumentors.

    ``service.name`` comes from ``OTEL_SERVICE_NAME`` when set, else the
    ``service_name`` argument. Instrumentors cover FastAPI apps passed via
    :func:`instrument_fastapi`, plus Redis, psycopg2, requests, and the
    GenAI/LLM hop.
    """
    global _configured
    if _configured:
        return
    _configured = True

    resource = Resource.create(
        {"service.name": os.getenv("OTEL_SERVICE_NAME", service_name)}
    )
    provider = TracerProvider(resource=resource)
    if os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"):
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(provider)

    RedisInstrumentor().instrument()
    Psycopg2Instrumentor().instrument()
    RequestsInstrumentor().instrument()

    # Guarded: the OpenLLMetry packages track langchain/pydantic churn and are
    # the likeliest import-time casualties — degrade to a warning, never crash.
    try:
        from opentelemetry.instrumentation.langchain import LangchainInstrumentor

        class _LangchainNoGraphWraps(LangchainInstrumentor):
            """Langchain instrumentor without the LangGraph component wraps.

            OpenLLMetry 0.62.3's ``_wrap_langgraph_components`` (Pregel
            stream/astream + Command + middleware hooks + agent factory wraps)
            silently kills agent middleware dispatch on the ASYNC path for
            langchain 1.3.x — ``_CapMiddleware.after_model`` and friends never
            execute, so cap enforcement and per-model counting die while the
            serving path itself keeps running (verified in isolation; the
            callback-manager and OpenAI function wraps are unaffected and are
            kept here). Skipped rather than reproducing all five internal
            wrap groups by hand, so the rest of the instrumentor stays
            up-to-date upstream.
            """

            def _wrap_langgraph_components(self, tracer):
                pass

        from opentelemetry.instrumentation.openai import OpenAIInstrumentor

        OpenAIInstrumentor().instrument()
        _LangchainNoGraphWraps().instrument()
    except Exception as exc:
        logging.getLogger(__name__).warning("GenAI instrumentors skipped: %s", exc)

    if log_filter:
        _install_log_filter()


def _install_log_filter() -> None:
    """Attach the trace filter to existing root handlers (or the root logger).

    Handler-level filters apply to records propagated to root from named
    loggers as well; a root-logger-level filter alone would not fire for them.
    """
    root = logging.getLogger()
    trace_filter = TraceContextLogFilter()
    handlers = [
        handler
        for handler in root.handlers
        if not any(isinstance(f, TraceContextLogFilter) for f in handler.filters)
    ]
    if handlers:
        for handler in handlers:
            handler.addFilter(trace_filter)
    else:
        root.addFilter(trace_filter)
