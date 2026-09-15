"""Phase 4 tripwire, unit part: W3C traceparent contracts (plan §6).

Pins the producer's inject-inside-produce-span contract and the consumer's
_extract_parent decode. The real-broker leg was removed: CI (ci.yml) runs
pytest with no Kafka service, so the integration leg could never run there.
"""

from __future__ import annotations

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from opentelemetry.trace import get_current_span


def _produce_headers():
    """Inject exactly the way ATMProducer._send does: inside the produce span."""
    from backend.kafka.producer import _propagator

    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(InMemorySpanExporter()))
    headers: dict[str, str] = {}
    with provider.get_tracer("test").start_as_current_span(
        "atm.events.produce"
    ) as span:
        _propagator.inject(carrier=headers)
        ctx = span.get_span_context()
    return headers, ctx


def test_inject_inside_produce_span_writes_own_ids():
    headers, ctx = _produce_headers()
    version, trace_id, span_id, flags = headers["traceparent"].split("-")
    assert version == "00" and len(flags) == 2
    assert trace_id == f"{ctx.trace_id:032x}"
    assert span_id == f"{ctx.span_id:016x}"


def test_extract_parent_resolves_produce_span():
    from backend.kafka.consumer import _extract_parent

    headers, ctx = _produce_headers()
    parent = _extract_parent([(k, v.encode("utf-8")) for k, v in headers.items()])
    remote = get_current_span(parent).get_span_context()
    assert remote.is_remote and remote.is_valid
    assert remote.span_id == ctx.span_id
    assert remote.trace_id == ctx.trace_id
    # Without a traceparent the consume side starts a fresh local trace.
    assert not get_current_span(_extract_parent([])).get_span_context().is_valid
