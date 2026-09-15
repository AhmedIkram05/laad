"""Phase 4: the atm.detect stage span projects a failed SageMaker cross-check.

ok=false must land on the span exactly like ok=true — stage-level
granularity, one attribute set (plan §4.2), no separate child span.
"""

from types import SimpleNamespace

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from opentelemetry.trace import StatusCode


def test_failed_sm_crosscheck_projected_on_detect_span(monkeypatch):
    import backend.kafka.consumer as consumer

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(consumer, "_tracer", provider.get_tracer("laad.kafka"))
    monkeypatch.setattr(
        consumer,
        "_cached_detector",
        SimpleNamespace(
            _loaded=True,
            detect_and_save=lambda: 0,
            sm_crosscheck={"ok": False, "endpoint": "e", "latency_ms": 5},
        ),
    )

    consumer._trigger_anomaly_detection()

    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].name == "atm.detect"
    attrs = spans[0].attributes
    assert attrs["laad.sm_crosscheck.ok"] is False
    assert attrs["laad.sm_crosscheck.endpoint"] == "e"
    assert attrs["laad.sm_crosscheck.latency_ms"] == 5
    assert attrs["laad.detect.models_loaded"] is True
    assert attrs["laad.detect.anomalies_saved"] == 0
    assert spans[0].status.status_code is not StatusCode.ERROR
