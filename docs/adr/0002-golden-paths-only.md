# 0002 — Auto-instrument broadly; hand-written spans only on two golden paths

**Status**: Accepted (2026-09-15) · [Plan](../observability-otel-plan.md)

Auto-instrumentation yields shallow spans (HTTP, Redis, DB, outgoing HTTP) nearly free across everything, but unbounded rich spans make demo traces unreadable and maintenance unbounded. We cap manual, business-qualified instrumentation at exactly two flows — the RAG query path and the synthetic event pipeline.

## Considered options

- **Rich manual spans on every endpoint and worker**: rejected — noise grows with surface area; the demo traces become unreadable and every new endpoint ships a modification to the telemetry.
- **RAG path only**: rejected — halves the story value; the pipeline flow (generate → produce → consume → detect → persist) is half the platform's real latency budget and half its interview story.

## Consequences

- The two paths' span names live in `docs/observability.md`; treat the list as a contract — keep names stable.
- A reader wanting rich tracing beyond the two paths must extend the golden-path list deliberately (this ADR is the gate), not opportunistically.
