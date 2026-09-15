# 0003 — AgentTrace is promoted to spans, not replaced

**Status**: Accepted (2026-09-15) · [Plan](../observability-otel-plan.md)

The agentic RAG layer already records one query's execution (mode, tool calls with duration and ok flags, rounds, model calls, latencies, retries) in-process and ships it in the API response. Replacing it with OpenTelemetry spans would break the existing response contract and couple in-process behavior to the telemetry stack.

We keep AgentTrace as the source of truth for what happened inside one query and generate spans/events from the **same points**: a root span per query, per-tool spans at the existing tool-recording point, cap decisions as events, and the already-computed latency split as attributes. Two representations of the same truth is deliberate: the dataclass serves the API and tests; the spans serve cross-service debuggability.

## Considered options

- **Replace AgentTrace** with OTel-only: rejected — bleeds the API contract and the tests, and health-checking would need reimplementation.
- **Keep both but with parallel capture logic**: rejected (early) — drift risk; capture must remain single-point.

## Consequences

- Future contributors should **not** "finish the migration" by deleting AgentTrace — it is load-bearing for the API and tests.
- Mapping table (AgentTrace field → span/event/attribute) lives in `docs/observability.md` once Phase 3 lands.
- Update [observability-otel-plan.md](../observability-otel-plan.md) phase 3 if the AgentTrace shape changes, not vice versa.
