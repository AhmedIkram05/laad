# LAAD — ATM Diagnostic Platform

LAAD is an ATM operations platform: synthetic ATM telemetry is generated, streamed through Kafka, scored by a detection engine, and surfaced with incidents answered by an agentic RAG assistant. This context defines the language of the observability layer added across it.

## Language

**Event**: One synthetic system-state message on the atm-events topic (status changes, hardware faults). _Avoid_: log line, signal.

**Metric**: One synthetic numeric-telemetry reading on the atm-metrics topic. _Avoid_: Prometheus metric, KPI.

**Detect Stage**: The periodic sweep where rule and ML detectors score incoming data and anomalies are persisted, coordinated by the distributed detection lock. _Avoid_: detector (an individual heuristic), gate.

**Gate Decision**: The outcome recorded when confidence thresholds (high/medium) route a RAG answer between answering and escalating. The thresholds are inputs; the decision is the observable. _Avoid_: hallucination check, confidence score.

**Agent Trace**: The in-process record of one RAG query's execution — mode, tool calls, rounds, model calls, latencies, retries. _Avoid_: run log, execution report.

**Query Trace**: The distributed OpenTelemetry trace covering one user-facing RAG query, including every tool, retrieval, and generation hop. _Avoid_: agent trace (that is the in-process record).

**Event Trace**: The distributed trace covering one synthetic event or metric from generation, through the broker, to consumption and persistence. _Avoid_: pipeline trace, flow trace.

**Golden Path**: One of exactly two flows carrying hand-written, rich spans — the RAG query path and the event pipeline path. _Avoid_: main flow, happy path.

**Span Promotion**: Mapping AgentTrace data onto OpenTelemetry spans and events instead of inventing a parallel telemetry stream. _Avoid_: dual telemetry, migration.

**Observability Boundary**: MLflow owns model-side telemetry (training, eval metrics); OpenTelemetry owns serving-path telemetry (requests, pipeline hops, gates). _Avoid_: unified stack, all-in-one tracing.
